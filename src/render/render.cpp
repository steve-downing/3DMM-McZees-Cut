/***************************************************************************
    3dmm-render: headless, deterministic .3mm movie renderer.  See render.h.

    Usage:
        3dmm-render <movie.3mm> <outdir> [--root <dir>] [--click-pause <sec>]
                    [--max-frames <n>] [--stereo] [--depth <percent>]

    --stereo renders each frame twice, from a left and a right eye, and
    writes them side by side (left | right) at double width. The actors
    (or, with none in view, the middle of the set) sit on the screen
    plane. --depth caps how far behind the screen the scene goes and --pop
    how far in front of it things come, as a percentage of picture width
    (defaults 2.5 and 1.5). --debug writes depth maps and depth stats.

    --root is the folder that contains the "3D Movie Maker" content folder
    (normally "C:\Program Files (x86)\Microsoft Kids"); it defaults to the
    folder the renderer lives in.

    Output (in <outdir>):
        frames\f000000.bmp ...  every distinct frame, 24-bit
        timeline.ffconcat       ffmpeg concat script with exact durations
        events.txt              transitions, pauses, and other playback events
        render.log              diagnostics
***************************************************************************/
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include "soc.h"
#include "midi.h"
#include "render.h"
#include "basepal.h"

ASSERTNAME

RTCLASS(RAPP)
RTCLASS(RSDV)

PTAGM vptagm;
RAPP vrapp;

const long kdxpRender = 544; // 3DMM's workspace size
const long kdypRender = 306;
const long kcbCacheTagm = 2048 * 1024;
const long kcbMovieCache = 256 * 1024;
const ulong kdtsTick = 5;                            // virtual milliseconds per loop iteration
const ulong kdtsTransition = 4 * kdtsSecond;         // matches kdtsTrans in movie.cpp
const long kcfrmTransition = 60;                     // synthesized frames per transition (15 fps)
const ulong kdtsMaxMovie = 2 * 60 * 60 * kdtsSecond; // give up after 2 hours of movie time
const ulong kdtsEndHold = kdtsSecond;                // how long to hold the final frame
const long kccmdMaxPerTick = 2000;                   // runaway guard for the command queue

/***************************************************************************
    Entry point.
***************************************************************************/
void FrameMain(void)
{
    vrapp.Run(fappOffscreen, fgobNil, kginMark);
    ExitProcess((UINT)vrapp.LwExitCode());
}

RAPP::RAPP(void)
{
    _dtsClickPause = 3 * kdtsSecond;
    _cfrmLimit = 0;
    _fStereo = fFalse;
    _pctDepth = 2.5;
    _pctPop = 1.5;
    _fDebug = fFalse;
    _fStereoValid = fFalse;
    _prgbEye = pvNil;
    _pglsndf = pvNil;
    _pglcue = pvNil;
    _pglvlmev = pvNil;
    _vlmMaster = kvlmFull;
    _pcfl = pvNil;
    _pmvie = pvNil;
    _pgptCapture = pvNil;
    _pglclrActive = pvNil;
    _pfileTimeline = pvNil;
    _pfileEvents = pvNil;
    _pfileLog = pvNil;
    _prgbPrev = pvNil;
    _prgbCur = pvNil;
    _prgbScratch = pvNil;
    _prgsuDissolve = pvNil;
    _fHavePrev = fFalse;
    _fCapturing = fFalse;
    _cfrmOut = 0;
    _tsStart = 0;
    _dtsShift = 0;
    _dtsPendingStart = 0;
    _ifrmPending = -1;
    _fInPause = fFalse;
    _tsPauseStart = 0;
    _lwExit = klwExitInit;
}

void RAPP::GetStnAppName(PSTN pstn)
{
    pstn->SetSz(PszLit("3dmm-render"));
}

/***************************************************************************
    Logging
***************************************************************************/
void RAPP::_Log(PSZ pszFormat, ...)
{
    va_list args;

    va_start(args, pszFormat);
    vfprintf(stdout, pszFormat, args);
    fputc('\n', stdout);
    fflush(stdout);
    va_end(args);

    if (pvNil != _pfileLog)
    {
        va_start(args, pszFormat);
        vfprintf(_pfileLog, pszFormat, args);
        fputc('\n', _pfileLog);
        fflush(_pfileLog);
        va_end(args);
    }
}

void RAPP::_Event(PSZ pszFormat, ...)
{
    va_list args;

    if (pvNil == _pfileEvents)
        return;
    fprintf(_pfileEvents, "%10.3f ", _DtsOut() / 1000.0);
    va_start(args, pszFormat);
    vfprintf(_pfileEvents, pszFormat, args);
    va_end(args);
    fputc('\n', _pfileEvents);
    fflush(_pfileEvents);
}

void RAPP::_LogEngineErrors(PSZ pszContext)
{
    long ierc;
    long cerc = vpers->Cerc();

    if (cerc == 0)
    {
        _Log("%s (no engine error codes)", pszContext);
        return;
    }
    for (ierc = 0; ierc < cerc; ierc++)
        _Log("%s: engine error code %ld", pszContext, vpers->ErcGet(ierc));
}

/***************************************************************************
    Headless: never put up an alert. Log it and answer "no".
***************************************************************************/
tribool RAPP::TGiveAlertSz(PSZ psz, long bk, long cok)
{
    _Log("alert suppressed: %s", psz);
    return tNo;
}

/***************************************************************************
    TAGM calls this when content for a source (product) can't be found.
    There is nobody to insert a CD, so record what was wanted and fail.
***************************************************************************/
bool RAPP::_FInsertCD(PSTN pstnTitle)
{
    vrapp._Log("missing content: %s", pstnTitle->Psz());
    vrapp._Event("missing-content %s", pstnTitle->Psz());
    vrapp._lwExit = klwExitMissingContent;
    return fFalse;
}

/***************************************************************************
    Init
***************************************************************************/
bool RAPP::_FInit(ulong grfapp, ulong grfgob, long ginDef)
{
    if (!_FParseCommandLine())
    {
        _lwExit = klwExitUsage;
        return fFalse;
    }
    if (!_FOpenOutput())
    {
        _lwExit = klwExitUsage;
        return fFalse;
    }
    if (!RAPP_PAR::_FInit(grfapp, grfgob, ginDef))
    {
        _Log("framework init failed");
        _lwExit = klwExitInit;
        return fFalse;
    }
    if (!_FInitContent())
    {
        _lwExit = klwExitInit;
        return fFalse;
    }
    if (!_FLoadMovie())
    {
        if (_lwExit != klwExitMissingContent)
            _lwExit = klwExitLoad;
        return fFalse;
    }
    return fTrue;
}

bool RAPP::_FParseCommandLine(void)
{
    long iarg;
    long carg = 0;
    char szExe[MAX_PATH];
    char *pchSlash;

    // default root: the folder this exe is in
    GetModuleFileNameA(NULL, szExe, MAX_PATH);
    pchSlash = strrchr(szExe, '\\');
    if (pchSlash != NULL)
        *pchSlash = 0;
    _stnRoot.SetSz(szExe);

    for (iarg = 1; iarg < __argc; iarg++)
    {
        char *psz = __argv[iarg];

        if (0 == strcmp(psz, "--root") && iarg + 1 < __argc)
            _stnRoot.SetSz(__argv[++iarg]);
        else if (0 == strcmp(psz, "--click-pause") && iarg + 1 < __argc)
            _dtsClickPause = (ulong)(atof(__argv[++iarg]) * kdtsSecond);
        else if (0 == strcmp(psz, "--max-frames") && iarg + 1 < __argc)
            _cfrmLimit = atol(__argv[++iarg]);
        else if (0 == strcmp(psz, "--stereo"))
            _fStereo = fTrue;
        else if (0 == strcmp(psz, "--depth") && iarg + 1 < __argc)
            _pctDepth = atof(__argv[++iarg]);
        else if (0 == strcmp(psz, "--pop") && iarg + 1 < __argc)
            _pctPop = atof(__argv[++iarg]);
        else if (0 == strcmp(psz, "--debug"))
            _fDebug = fTrue;
        else if (carg == 0)
        {
            _stnMovie.SetSz(psz);
            carg++;
        }
        else if (carg == 1)
        {
            _stnOutDir.SetSz(psz);
            carg++;
        }
        else
        {
            carg = -1;
            break;
        }
    }

    if (carg != 2)
    {
        fprintf(stderr, "usage: 3dmm-render <movie.3mm> <outdir> [--root <dir>] [--click-pause <sec>] "
                        "[--max-frames <n>] [--stereo] [--depth <percent>] [--pop <percent>] [--debug]\n");
        return fFalse;
    }
    return fTrue;
}

bool RAPP::_FOpenOutput(void)
{
    STN stn;

    CreateDirectoryA(_stnOutDir.Psz(), NULL);
    stn = _stnOutDir;
    stn.FAppendSz(PszLit("\\frames"));
    CreateDirectoryA(stn.Psz(), NULL);

    stn = _stnOutDir;
    stn.FAppendSz(PszLit("\\render.log"));
    _pfileLog = fopen(stn.Psz(), "w");

    stn = _stnOutDir;
    stn.FAppendSz(PszLit("\\events.txt"));
    _pfileEvents = fopen(stn.Psz(), "w");

    stn = _stnOutDir;
    stn.FAppendSz(PszLit("\\timeline.ffconcat"));
    _pfileTimeline = fopen(stn.Psz(), "w");

    if (pvNil == _pfileLog || pvNil == _pfileEvents || pvNil == _pfileTimeline)
    {
        fprintf(stderr, "can't write to output folder %s\n", _stnOutDir.Psz());
        return fFalse;
    }
    fprintf(_pfileTimeline, "ffconcat version 1.0\n");

    stn = _stnOutDir;
    stn.FAppendSz(PszLit("\\sounds"));
    CreateDirectoryA(stn.Psz(), NULL);
    _pglsndf = GL::PglNew(size(SNDF));
    _pglcue = GL::PglNew(size(CUE));
    _pglvlmev = GL::PglNew(size(VLMEV));
    if (pvNil == _pglsndf || pvNil == _pglcue || pvNil == _pglvlmev)
        return fFalse;
    _Log("movie: %s", _stnMovie.Psz());
    _Log("content root: %s", _stnRoot.Psz());
    if (_fStereo)
        _Log("stereo: side-by-side, depth %.2f%%, pop %.2f%%", _pctDepth, _pctPop);
    return fTrue;
}

/***************************************************************************
    No visible window, no menus.
***************************************************************************/
bool RAPP::_FInitOS(void)
{
    vwig.wShow = SW_HIDE;
    return RAPP_PAR::_FInitOS();
}

bool RAPP::_FInitMenu(void)
{
    return fTrue;
}

/***************************************************************************
    A sound manager whose devices are RSDVs: the engine plays sounds as
    usual, nothing comes out of the speakers, and every sound becomes a
    cue in the audio script.
***************************************************************************/
bool RAPP::_FInitSound(long wav)
{
    PSNDV psndv;

    if (pvNil == vpsndm)
        vpsndm = SNDM::PsndmNew();
    if (pvNil == vpsndm)
        return fTrue;
    if (pvNil != (psndv = NewObj RSDV(kctgWave)))
    {
        vpsndm->FAddDevice(kctgWave, psndv);
        ReleasePpo(&psndv);
    }
    if (pvNil != (psndv = NewObj RSDV(kctgMidi)))
    {
        vpsndm->FAddDevice(kctgMidi, psndv);
        ReleasePpo(&psndv);
    }
    return fTrue;
}

/***************************************************************************
    Set up the tag manager (content lookup), the 3DMM resource file, the
    shade table, 3-D text action names, and the base palette. This is the
    subset of APP::_FInit that the movie engine actually depends on.
***************************************************************************/
bool RAPP::_FInitContent(void)
{
    FNI fniRoot, fniProduct, fniChk;
    STN stn;
    PGST pgst = pvNil;
    long sid;
    BLCK blck;
    short bo, osk;
    PGL pglclr;

    stn = _stnRoot;
    if (stn.Cch() == 0 || stn.Psz()[stn.Cch() - 1] != '\\')
        stn.FAppendSz(PszLit("\\"));
    if (!fniRoot.FBuildFromPath(&stn, kftgDir))
    {
        _Log("bad content root: %s", stn.Psz());
        return fFalse;
    }

    fniProduct = fniRoot;
    stn.SetSz(PszLit("3D Movie Maker"));
    if (!fniProduct.FDownDir(&stn, ffniMoveToDir))
    {
        _Log("no \"3D Movie Maker\" folder under %s", _stnRoot.Psz());
        return fFalse;
    }

    vptagm = TAGM::PtagmNew(&fniRoot, RAPP::_FInsertCD, kcbCacheTagm);
    if (pvNil == vptagm)
    {
        _Log("TAGM::PtagmNew failed");
        return fFalse;
    }
    if (pvNil == (pgst = GST::PgstNew(size(long))))
        return fFalse;
    stn.SetSz(PszLit("3D Movie Maker/3DMovie"));
    sid = 1;
    if (!pgst->FAddStn(&stn, &sid) || !vptagm->FMergeGstSource(pgst, kboCur, koskCur))
    {
        ReleasePpo(&pgst);
        _Log("couldn't register the 3D Movie Maker content source");
        return fFalse;
    }
    ReleasePpo(&pgst);

    // the 3DMM resource file (built from src/studio/utest.cht)
    fniChk = fniProduct;
    stn.SetSz(PszLit("3DMovie"));
    if (!fniChk.FSetLeaf(&stn, kftgChunky) || tYes != fniChk.TExists())
    {
        fniChk = fniProduct;
        stn.SetSz(PszLit("3D Movie Maker"));
        if (!fniChk.FSetLeaf(&stn, kftgChunky) || tYes != fniChk.TExists())
        {
            _Log("can't find 3DMovie.chk in the 3D Movie Maker folder");
            return fFalse;
        }
    }
    if (pvNil == (_pcfl = CFL::PcflOpen(&fniChk, fcflNil)))
    {
        _Log("can't open 3DMovie.chk");
        return fFalse;
    }

    if (!_pcfl->FFind(kctgGst, kcnoGstAction, &blck) || pvNil == (pgst = GST::PgstRead(&blck, &bo, &osk)))
    {
        _Log("can't read 3-D text action names");
        return fFalse;
    }
    if (!TDT::FSetActionNames(pgst))
    {
        ReleasePpo(&pgst);
        _Log("TDT::FSetActionNames failed");
        return fFalse;
    }
    ReleasePpo(&pgst);

    if (!MTRL::FSetShadeTable(_pcfl, kctgTmap, 0))
    {
        _Log("MTRL::FSetShadeTable failed");
        return fFalse;
    }

    if (pvNil == (pglclr = GL::PglNew(size(CLR), 256)) || !pglclr->FSetIvMac(256))
    {
        ReleasePpo(&pglclr);
        return fFalse;
    }
    CopyPb((void *)kclrBasePalette, pglclr->QvGet(0), size(kclrBasePalette));
    GPT::SetActiveColors(pglclr, fpalIdentity);
    ReleasePpo(&pglclr);
    _pglclrActive = GPT::PglclrGetPalette();

    return fTrue;
}

/***************************************************************************
    Open the movie and give it a view (an MVU gob on the hidden screen).
***************************************************************************/
bool RAPP::_FLoadMovie(void)
{
    FNI fni;
    PMCC pmcc;
    GCB gcb;
    RC rcAbs(0, 0, kdxpRender, kdypRender);
    RC rcRel(0, 0, 0, 0);
    STN stn = _stnMovie;
    long cpx = _DxpOut() * kdypRender;
    long ipx;
    ulong luRnd = 0x3D3D3D3D;

    if (!fni.FBuildFromPath(&stn, kftg3mm) || tYes != fni.TExists())
    {
        _Log("can't find movie %s", _stnMovie.Psz());
        return fFalse;
    }

    if (pvNil == (pmcc = NewObj MCC(kdxpRender, kdypRender, kcbMovieCache)))
        return fFalse;
    _pmvie = MVIE::PmvieNew(fFalse, pmcc, &fni, cnoNil);
    ReleasePpo(&pmcc);
    if (pvNil == _pmvie)
    {
        _Log("couldn't open the movie");
        _LogEngineErrors("open");
        return fFalse;
    }

    gcb.Set(CMH::HidUnique(), GOB::PgobScreen(), fgobNil, kginMark, &rcAbs, &rcRel);
    if (pvNil == _pmvie->PddgNew(&gcb))
    {
        _Log("couldn't create the movie view");
        _LogEngineErrors("view");
        return fFalse;
    }

    _Log("scenes: %ld", _pmvie->Cscen());
    if (_pmvie->Cscen() <= 0)
    {
        _Log("movie has no scenes");
        return fFalse;
    }
    if (!_pmvie->FSwitchScen(0))
    {
        _Log("couldn't load the first scene");
        _LogEngineErrors("scene 0");
        return fFalse;
    }

    if (pvNil == (_pgptCapture = GPT::PgptNewOffscreen(&rcAbs, 8)))
        return fFalse;

    _prgbEye = (byte *)malloc(kdxpRender * kdypRender * 3);
    _prgbPrev = (byte *)malloc(cpx * 3);
    _prgbCur = (byte *)malloc(cpx * 3);
    _prgbScratch = (byte *)malloc(cpx * 3);
    _prgsuDissolve = (ushort *)malloc(cpx * size(ushort));
    if (pvNil == _prgbEye || pvNil == _prgbPrev || pvNil == _prgbCur || pvNil == _prgbScratch ||
        pvNil == _prgsuDissolve)
        return fFalse;

    // fixed per-pixel dissolve order, so dissolves look the same every run
    for (ipx = 0; ipx < cpx; ipx++)
    {
        luRnd ^= luRnd << 13;
        luRnd ^= luRnd >> 17;
        luRnd ^= luRnd << 5;
        _prgsuDissolve[ipx] = (ushort)(luRnd >> 16);
    }
    return fTrue;
}

/***************************************************************************
    Main loop: render the movie, then quit.
***************************************************************************/
void RAPP::_Loop(void)
{
    _lwExit = _FRender() ? klwExitOk : (_lwExit == klwExitOk ? klwExitRender : _lwExit);
    _fQuit = fTrue;
}

bool RAPP::_FRender(void)
{
    // Freeze the application clock; from here on time only moves when we
    // say so, which makes the engine's own timers deterministic.
    vpusac->Scale(0);
    _tsStart = TsCurrent();
    _lwExit = klwExitOk;
    _fCapturing = fTrue;

    _pmvie->Play();
    if (!_pmvie->FPlaying())
    {
        _Log("movie refused to start playing");
        _LogEngineErrors("play");
        return fFalse;
    }
    _Event("play");

    while (_pmvie->FPlaying())
    {
        if (TsCurrent() - _tsStart > kdtsMaxMovie)
        {
            _Log("gave up: movie still playing after %lu seconds of movie time", kdtsMaxMovie / kdtsSecond);
            _lwExit = klwExitTimeout;
            return fFalse;
        }
        if (_cfrmLimit > 0 && _cfrmOut >= _cfrmLimit)
        {
            _Log("stopping at --max-frames %ld", _cfrmLimit);
            break;
        }
        vpusac->Jump(kdtsTick);
        _pmvie->SetFIdleSeen(fTrue);
        _Pump();
        _HandlePause();
    }

    // one last look, in case the final frame never got flushed
    _Capture();
    _fCapturing = fFalse;
    _FinishTimeline(_DtsOut() + kdtsEndHold);
    _WriteAudioScript(_DtsOut() + kdtsEndHold);
    _Event("end");
    _Log("done: %ld frames, %.2f seconds", _cfrmOut, _DtsOut() / 1000.0);
    return _lwExit == klwExitOk;
}

/***************************************************************************
    Run everything that's due: OS messages (the hidden window), then
    the command queue, which is where clock alarms and the movie's
    per-frame render commands are delivered.
***************************************************************************/
void RAPP::_Pump(void)
{
    MSG msg;
    long ccmd;

    while (PeekMessage(&msg, hNil, 0, 0, PM_REMOVE))
    {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    vpcex->EnqueueCid(cidIdle);
    for (ccmd = 0; ccmd < kccmdMaxPerTick && vpcex->FDispatchNextCmd(); ccmd++)
        ;
}

/***************************************************************************
    "Wait for a click" pauses: nobody's going to click, so hold the frame
    for _dtsClickPause and then continue, exactly the way MVU does when
    it sees a mouse click during a pause.
***************************************************************************/
void RAPP::_HandlePause(void)
{
    PMVU pmvu = _pmvie->PmvuCur();

    if (pvNil == pmvu || !pmvu->FPausing())
    {
        _fInPause = fFalse;
        return;
    }
    if (!_fInPause)
    {
        _fInPause = fTrue;
        _tsPauseStart = TsCurrent();
        _Event("pause-until-click");
        return;
    }
    if (TsCurrent() - _tsPauseStart >= _dtsClickPause)
    {
        _fInPause = fFalse;
        _Event("auto-click");
        _pmvie->Pclok()->FSetAlarm(0, _pmvie);
    }
}

/***************************************************************************
    The engine flushes each finished frame with UpdateMarked. Grab the
    frame first, then let the framework do its normal (invisible) update.
***************************************************************************/
void RAPP::UpdateMarked(void)
{
    if (_fCapturing)
        _Capture();
    RAPP_PAR::UpdateMarked();
}

ulong RAPP::_DtsOut(void)
{
    return TsCurrent() - _tsStart;
}

/***************************************************************************
    Base palette with the current background's palette laid over it, the
    same merge MVIE::DoTrans does. Applied as the active palette so every
    offscreen port (including BWLD's) agrees on what each index means.
***************************************************************************/
void RAPP::_UpdatePalette(void)
{
    PGL pglclr, pglclrBkgd = pvNil;
    long iclrMin = 0;

    if (pvNil == (pglclr = GL::PglNew(size(CLR), 256)) || !pglclr->FSetIvMac(256))
    {
        ReleasePpo(&pglclr);
        return;
    }
    CopyPb((void *)kclrBasePalette, pglclr->QvGet(0), size(kclrBasePalette));

    if (pvNil != _pmvie->Pscen() && _pmvie->Pscen()->Pbkgd()->FGetPalette(&pglclrBkgd, &iclrMin) &&
        pglclrBkgd->IvMac() > 0 && pglclrBkgd->IvMac() + iclrMin <= 256)
    {
        CopyPb(pglclrBkgd->QvGet(0), pglclr->QvGet(iclrMin), LwMul(size(CLR), pglclrBkgd->IvMac()));
    }
    ReleasePpo(&pglclrBkgd);

    if (pvNil == _pglclrActive || _pglclrActive->IvMac() != 256 ||
        !FEqualRgb(_pglclrActive->QvGet(0), pglclr->QvGet(0), 256 * size(CLR)))
    {
        GPT::SetActiveColors(pglclr, fpalIdentity);
        ReleasePpo(&_pglclrActive);
        _pglclrActive = GPT::PglclrGetPalette();
    }
    ReleasePpo(&pglclr);
}

/***************************************************************************
    Copy the capture port out as 24-bit RGB (top-down).
***************************************************************************/
void RAPP::_ConvertCapture(byte *prgbDst)
{
    RC rc;
    byte *prgbSrc;
    long cbRow, xp, yp;
    CLR *prgclr;
    CLR clr;

    prgbSrc = _pgptCapture->PrgbLockPixels(&rc);
    if (pvNil == prgbSrc)
        return;
    cbRow = _pgptCapture->CbRow();
    prgclr = (CLR *)_pglclrActive->QvGet(0);
    for (yp = 0; yp < kdypRender; yp++)
    {
        byte *pbSrc = prgbSrc + yp * cbRow;
        byte *pbDst = prgbDst + yp * kdxpRender * 3;
        for (xp = 0; xp < kdxpRender; xp++)
        {
            clr = prgclr[pbSrc[xp]];
            *pbDst++ = clr.bRed;
            *pbDst++ = clr.bGreen;
            *pbDst++ = clr.bBlue;
        }
    }
    _pgptCapture->Unlock();
}

/***************************************************************************
    Copy a kdxpRender-wide RGB image into one half of a side-by-side
    frame, moved dxpShift pixels sideways (the stereo window shift that
    puts the convergence depth on the screen plane). Exposed edges are
    black.
***************************************************************************/
void RAPP::_PlaceEye(byte *prgbEye, byte *prgbFrame, long ieye, long dxpShift)
{
    long yp, xpDst, xpSrc;
    long cbRowFrame = _DxpOut() * 3;

    for (yp = 0; yp < kdypRender; yp++)
    {
        byte *pbDst = prgbFrame + yp * cbRowFrame + ieye * kdxpRender * 3;
        byte *pbSrc = prgbEye + yp * kdxpRender * 3;
        for (xpDst = 0; xpDst < kdxpRender; xpDst++)
        {
            xpSrc = xpDst - dxpShift;
            if (xpSrc < 0 || xpSrc >= kdxpRender)
                FillPb(pbDst + xpDst * 3, 3, 0);
            else
                CopyPb(pbSrc + xpSrc * 3, pbDst + xpDst * 3, 3);
        }
    }
}

/***************************************************************************
    Draw the movie view into _prgbCur: once for mono, or once per eye for
    stereo.
***************************************************************************/
void RAPP::_DrawFrame(PMVU pmvu)
{
    PBWLD pbwld = _pmvie->Pbwld();
    BMAT34 bmat34;
    long ieye;

    if (!_fStereo)
    {
        pmvu->DrawTree(_pgptCapture, pvNil, pvNil, fgobNil);
        _ConvertCapture(_prgbCur);
        return;
    }

    if (pvNil == _pmvie->Pscen() || pvNil == pbwld)
    {
        _DrawFlatStereo(pmvu);
        return;
    }

    // Stereo parameters are chosen once per camera view, from its first
    // frame, so depth doesn't "breathe" as actors move around.
    pbwld->Render();
    pbwld->GetCamera(&bmat34);
    if (!_fStereoValid || !FEqualRgb(&bmat34, &_bmat34Stereo, size(BMAT34)))
    {
        double dzrConverge, dzrNear, dzrFar, kFar, kNear, dxr;
        double dxpFar = _pctDepth / 100.0 * kdxpRender;
        double dxpNear = _pctPop / 100.0 * kdxpRender;

        _bmat34Stereo = bmat34;
        _fStereoValid = fTrue;
        _dxrEye = 0;
        _dxpShift = 0;
        if (pbwld->FGetStereoGeometry(&dzrConverge, &dzrNear, &dzrFar, &_dxpFocal))
        {
            // eye separation: as wide as the far and near budgets allow
            kFar = 1.0 / dzrConverge - 1.0 / dzrFar;
            kNear = 1.0 / dzrNear - 1.0 / dzrConverge;
            _dxrEye = 1e30;
            if (kFar > 1e-12)
                _dxrEye = dxpFar / (_dxpFocal * kFar);
            if (kNear > 1e-12 && (dxr = dxpNear / (_dxpFocal * kNear)) < _dxrEye)
                _dxrEye = dxr;
            if (_dxrEye >= 1e29)
                _dxrEye = 0;
            _dxpShift = (long)(_dxrEye * _dxpFocal / (2 * dzrConverge) + 0.5);
            _Event("stereo view: converge=%.1f near=%.1f far=%.1f focal=%.0fpx eye=%.3f shift=%ldpx", dzrConverge,
                   dzrNear, dzrFar >= 1e8 ? -1.0 : dzrFar, _dxpFocal, _dxrEye, _dxpShift);
            if (_fDebug)
                _DumpStereoDebug(pbwld);
        }
        else
        {
            // nothing with depth in view yet (e.g. 3-D text still to come);
            // stay flat and look again next frame
            _fStereoValid = fFalse;
        }
    }

    if (_dxrEye <= 0)
    {
        _DrawFlatStereo(pmvu);
        return;
    }

    for (ieye = 0; ieye < 2; ieye++)
    {
        double dxr = (ieye == 0) ? -_dxrEye / 2 : _dxrEye / 2;
        if (!pbwld->FRenderEye(dxr, _dxpFocal))
            _Log("stereo: eye render failed; using mono for this eye");
        pmvu->DrawTree(_pgptCapture, pvNil, pvNil, fgobNil);
        _ConvertCapture(_prgbEye);
        _PlaceEye(_prgbEye, _prgbCur, ieye, (ieye == 0) ? -_dxpShift : _dxpShift);
    }
    pbwld->EndStereo();
}

// both eyes the same picture (no 3-D world, or no usable depth)
void RAPP::_DrawFlatStereo(PMVU pmvu)
{
    pmvu->DrawTree(_pgptCapture, pvNil, pvNil, fgobNil);
    _ConvertCapture(_prgbEye);
    _PlaceEye(_prgbEye, _prgbCur, 0, 0);
    _PlaceEye(_prgbEye, _prgbCur, 1, 0);
}

void RAPP::_DumpStereoDebug(PBWLD pbwld)
{
    double dzrHither, dzrYon, radFov;
    long rgsuB[11], rgsuA[11];
    char szPath[MAX_PATH];

    pbwld->GetCameraParams(&dzrHither, &dzrYon, &radFov);
    pbwld->GetDepthStats(fFalse, rgsuB, 10);
    pbwld->GetDepthStats(fTrue, rgsuA, 10);
    _Event("camera hither=%.4f yon=%.4f fov=%.2fdeg", dzrHither, dzrYon, radFov * 180 / 3.14159265);
    _Event("bkgd Z deciles %ld %ld %ld %ld %ld %ld %ld %ld %ld %ld %ld", rgsuB[0], rgsuB[1], rgsuB[2], rgsuB[3],
           rgsuB[4], rgsuB[5], rgsuB[6], rgsuB[7], rgsuB[8], rgsuB[9], rgsuB[10]);
    _Event("actor Z deciles %ld %ld %ld %ld %ld %ld %ld %ld %ld %ld %ld", rgsuA[0], rgsuA[1], rgsuA[2], rgsuA[3],
           rgsuA[4], rgsuA[5], rgsuA[6], rgsuA[7], rgsuA[8], rgsuA[9], rgsuA[10]);
    pbwld->LogDepthCalibration(_pfileEvents);
    _snprintf(szPath, MAX_PATH, "%s\\depth-%06ld-bkgd.pgm", _stnOutDir.Psz(), _cfrmOut);
    pbwld->FDumpDepth(szPath, fFalse);
    _snprintf(szPath, MAX_PATH, "%s\\depth-%06ld-work.pgm", _stnOutDir.Psz(), _cfrmOut);
    pbwld->FDumpDepth(szPath, fTrue);
}

void RAPP::_Capture(void)
{
    PMVU pmvu;
    TRANS trans;
    ulong dtsOut;
    byte *prgbT;
    long cb = _DxpOut() * kdypRender * 3;

    if (pvNil == _pmvie || pvNil == _pgptCapture || pvNil == (pmvu = _pmvie->PmvuCur()))
        return;

    // Animated transitions are synthesized below rather than run, so
    // clear the request before anything tries to animate it.
    trans = _pmvie->Trans();
    if (trans != transNil)
        _pmvie->SetTrans(transNil);

    _UpdatePalette();
    _DrawFrame(pmvu);
    if (trans == transBlack)
        ClearPb(_prgbCur, cb);

    if (_fHavePrev && trans == transNil && FEqualRgb(_prgbPrev, _prgbCur, cb))
        return;

    dtsOut = _DtsOut();
    if (_fHavePrev && (trans == transFadeToBlack || trans == transFadeToWhite || trans == transDissolve))
    {
        _EmitTransition(trans, dtsOut);
        dtsOut = _DtsOut();
    }
    else if (trans != transNil)
        _Event("transition %s", trans == transBlack ? "black" : "cut");

    if (!_FEmitFrame(_prgbCur, dtsOut))
    {
        _fCapturing = fFalse;
        _lwExit = klwExitRender;
        _pmvie->SetFStopPlaying(fTrue);
        return;
    }

    prgbT = _prgbPrev;
    _prgbPrev = _prgbCur;
    _prgbCur = prgbT;
    _fHavePrev = fTrue;
}

/***************************************************************************
    Synthesize an animated transition from _prgbPrev to _prgbCur, using
    the same pixel-dissolve approach as GNV::Dissolve. Fades go to the
    solid color in the first half and out of it in the second.
***************************************************************************/
void RAPP::_EmitTransition(long trans, ulong dtsOut)
{
    long ifrm, ipx;
    long cpx = _DxpOut() * kdypRender;
    long cfrmHalf = kcfrmTransition / 2;
    byte bFill = (trans == transFadeToWhite) ? 0xFF : 0x00;

    _Event("transition %s",
           trans == transDissolve ? "dissolve" : (trans == transFadeToWhite ? "fade-white" : "fade-black"));

    for (ifrm = 0; ifrm < kcfrmTransition; ifrm++)
    {
        ulong dts = dtsOut + LwMulDiv(ifrm, kdtsTransition, kcfrmTransition);

        if (trans == transDissolve)
        {
            // pixels whose key falls under the threshold have switched
            ulong suThresh = (ulong)LwMulDiv(ifrm + 1, 0x10000, kcfrmTransition);
            for (ipx = 0; ipx < cpx; ipx++)
            {
                byte *pbSrc = (_prgsuDissolve[ipx] < suThresh) ? _prgbCur : _prgbPrev;
                CopyPb(pbSrc + ipx * 3, _prgbScratch + ipx * 3, 3);
            }
        }
        else
        {
            bool fIn = ifrm >= cfrmHalf;
            long ifrmHalf = fIn ? ifrm - cfrmHalf : ifrm;
            ulong suThresh = (ulong)LwMulDiv(ifrmHalf + 1, 0x10000, cfrmHalf);
            byte *pbFrom = fIn ? pvNil : _prgbPrev;
            byte *pbTo = fIn ? _prgbCur : pvNil;

            for (ipx = 0; ipx < cpx; ipx++)
            {
                byte *pbSrc = (_prgsuDissolve[ipx] < suThresh) ? pbTo : pbFrom;
                if (pvNil == pbSrc)
                    FillPb(_prgbScratch + ipx * 3, 3, bFill);
                else
                    CopyPb(pbSrc + ipx * 3, _prgbScratch + ipx * 3, 3);
            }
        }
        _FEmitFrame(_prgbScratch, dts);
    }
    // the real dissolve blocks for kdtsTransition; let the same amount
    // of movie time pass so sounds and timers line up with the picture
    vpusac->Jump(kdtsTransition);
}

/***************************************************************************
    Timeline bookkeeping. A frame's duration is only known once the next
    frame shows up, so the newest frame stays pending until then.
***************************************************************************/
void RAPP::_FlushPendingFrame(ulong dtsOutNext)
{
    if (_ifrmPending < 0)
        return;
    fprintf(_pfileTimeline, "file 'frames/f%06ld.bmp'\nduration %.3f\n", _ifrmPending,
            (dtsOutNext - _dtsPendingStart) / 1000.0);
    _ifrmPending = -1;
}

bool RAPP::_FEmitFrame(byte *prgb, ulong dtsOut)
{
    STN stn;
    char szPath[MAX_PATH];
    long ifrm;

    if (_ifrmPending >= 0 && dtsOut <= _dtsPendingStart)
    {
        // replaces a frame that never got any screen time
        ifrm = _ifrmPending;
    }
    else
    {
        _FlushPendingFrame(dtsOut);
        ifrm = _cfrmOut++;
        _ifrmPending = ifrm;
        _dtsPendingStart = dtsOut;
    }

    _snprintf(szPath, MAX_PATH, "%s\\frames\\f%06ld.bmp", _stnOutDir.Psz(), ifrm);
    szPath[MAX_PATH - 1] = 0;
    stn.SetSz(szPath);
    if (!_FWriteBmp(&stn, prgb))
    {
        _Log("can't write %s", stn.Psz());
        return fFalse;
    }
    return fTrue;
}

void RAPP::_FinishTimeline(ulong dtsOutEnd)
{
    long ifrmLast = _ifrmPending;

    if (pvNil == _pfileTimeline)
        return;
    _FlushPendingFrame(dtsOutEnd);
    // the concat demuxer ignores the last entry's duration unless the
    // file is listed once more
    if (ifrmLast >= 0)
        fprintf(_pfileTimeline, "file 'frames/f%06ld.bmp'\n", ifrmLast);
    fclose(_pfileTimeline);
    _pfileTimeline = pvNil;
}

bool RAPP::_FWriteBmp(PSTN pstnFile, byte *prgb)
{
    FILE *pfile;
    byte rgbHeader[54];
    long dxp = _DxpOut();
    long cbRow = dxp * 3; // 544 and 1088 are multiples of 4
    long cbImage = cbRow * kdypRender;
    long cbFile = size(rgbHeader) + cbImage;
    long yp, xp;
    byte rgbRow[2 * kdxpRender * 3];

    ClearPb(rgbHeader, size(rgbHeader));
    rgbHeader[0] = 'B';
    rgbHeader[1] = 'M';
    *(long *)(rgbHeader + 2) = cbFile;
    *(long *)(rgbHeader + 10) = size(rgbHeader);
    *(long *)(rgbHeader + 14) = 40;
    *(long *)(rgbHeader + 18) = dxp;
    *(long *)(rgbHeader + 22) = kdypRender; // bottom-up
    *(short *)(rgbHeader + 26) = 1;
    *(short *)(rgbHeader + 28) = 24;
    *(long *)(rgbHeader + 34) = cbImage;

    if (pvNil == (pfile = fopen(pstnFile->Psz(), "wb")))
        return fFalse;
    fwrite(rgbHeader, 1, size(rgbHeader), pfile);
    for (yp = kdypRender - 1; yp >= 0; yp--)
    {
        byte *pbSrc = prgb + yp * cbRow;
        for (xp = 0; xp < dxp; xp++)
        {
            rgbRow[xp * 3 + 0] = pbSrc[xp * 3 + 2];
            rgbRow[xp * 3 + 1] = pbSrc[xp * 3 + 1];
            rgbRow[xp * 3 + 2] = pbSrc[xp * 3 + 0];
        }
        fwrite(rgbRow, 1, cbRow, pfile);
    }
    return 0 == fclose(pfile);
}

/***************************************************************************
    Clean up
***************************************************************************/
void RAPP::_CleanUp(void)
{
    _fCapturing = fFalse;
    if (pvNil != _pfileTimeline)
        _FinishTimeline(_DtsOut() + kdtsEndHold);
    if (pvNil != _pfileEvents)
        fclose(_pfileEvents);
    _pfileEvents = pvNil;
    _Log("exit code %ld", _lwExit);
    if (pvNil != _pfileLog)
        fclose(_pfileLog);
    _pfileLog = pvNil;

    // Everything we produce is on disk. Tearing down the engine, gob tree
    // and BRender in the right order buys nothing for a one-shot process
    // (and the default order crashes), so let the OS reclaim it all.
    fflush(stdout);
    ExitProcess((UINT)_lwExit);
}

/***************************************************************************
    Sound bookkeeping.
***************************************************************************/
void RSDV::SetVlm(long vlm)
{
    vrapp.SetMasterVlm(vlm);
}

long RSDV::VlmCur(void)
{
    return vrapp.VlmMaster();
}

long RSDV::SiiPlay(PRCA prca, CTG ctg, CNO cno, long sqn, long vlm, long cactPlay, ulong dtsStart, long spr, long scl)
{
    return vrapp.SiiPlaySound(_ctg, prca, ctg, cno, sqn, vlm, cactPlay, dtsStart, scl);
}

void RSDV::Stop(long sii)
{
    vrapp.StopSounds(_ctg, sii, sqnNil, sclNil);
}

void RSDV::StopAll(long sqn, long scl)
{
    vrapp.StopSounds(_ctg, siiNil, sqn, scl);
}

bool RSDV::FPlaying(long sii)
{
    return vrapp.FSoundsPlaying(_ctg, sii, sqnNil, sclNil);
}

bool RSDV::FPlayingAll(long sqn, long scl)
{
    return vrapp.FSoundsPlaying(_ctg, siiNil, sqn, scl);
}

const long kcactLoopForever = 1000; // MSND loops with klwMax

void RAPP::SetMasterVlm(long vlm)
{
    VLMEV vlmev;

    if (vlm == _vlmMaster)
        return; // SNDM tells every device; record each change once
    _vlmMaster = vlm;
    if (pvNil == _pglvlmev || !_fCapturing)
        return;
    vlmev.ts = _DtsOut();
    vlmev.vlm = vlm;
    _pglvlmev->FAdd(&vlmev);
}

/***************************************************************************
    Register a sound (extracting it the first time we see it) and add a
    cue. Queued sounds start when the queue's previous sound ends.
***************************************************************************/
long RAPP::SiiPlaySound(CTG ctgDev, PRCA prca, CTG ctg, CNO cno, long sqn, long vlm, long cactPlay, ulong dtsStart,
                        long scl)
{
    PCRF pcrf;
    SNDF sndf;
    CUE cue, cueT;
    long isndf, icue;
    ulong tsNow = _DtsOut();

    if (pvNil == _pglsndf || pvNil == _pglcue || pvNil == prca)
        return siiNil;
    if (pvNil == (pcrf = prca->PcrfFindChunk(ctg, cno)))
    {
        _Event("sound-missing %c%c%c%c %ld", (char)(ctg >> 24), (char)(ctg >> 16), (char)(ctg >> 8), (char)ctg, cno);
        return siiNil;
    }

    for (isndf = 0; isndf < _pglsndf->IvMac(); isndf++)
    {
        _pglsndf->Get(isndf, &sndf);
        if (sndf.pcrf == pcrf && sndf.ctg == ctg && sndf.cno == cno)
            break;
    }
    if (isndf == _pglsndf->IvMac())
    {
        sndf.pcrf = pcrf;
        sndf.ctg = ctg;
        sndf.cno = cno;
        sndf.dtsLen = 0;
        if (!_FWriteSoundFile(&sndf, isndf))
            _Log("couldn't extract sound %ld", cno);
        if (!_pglsndf->FAdd(&sndf))
            return siiNil;
    }

    ClearPb(&cue, size(cue));
    cue.sii = RSDV::SiiNew();
    cue.isndf = isndf;
    cue.ctgDev = ctgDev;
    cue.sqn = sqn;
    cue.scl = scl;
    cue.vlm = vlm;
    cue.cactPlay = cactPlay;
    cue.dtsOffset = dtsStart;
    cue.tsStart = tsNow;
    if (sqn != ksqnNone)
    {
        for (icue = 0; icue < _pglcue->IvMac(); icue++)
        {
            _pglcue->Get(icue, &cueT);
            if (cueT.ctgDev == ctgDev && cueT.sqn == sqn && cueT.tsEnd > cue.tsStart && cueT.tsEnd != kluMax)
                cue.tsStart = cueT.tsEnd;
        }
    }
    if (cactPlay <= 0 || cactPlay >= kcactLoopForever || sndf.dtsLen == 0)
        cue.tsEnd = (sndf.dtsLen == 0 && cactPlay > 0 && cactPlay < kcactLoopForever) ? cue.tsStart : kluMax;
    else
        cue.tsEnd = cue.tsStart + LwMax(0, (long)(sndf.dtsLen * cactPlay) - (long)dtsStart);
    if (!_pglcue->FAdd(&cue))
        return siiNil;
    _Event("sound s%03ld vlm=%ld loops=%ld offset=%lu", isndf, vlm, cactPlay, dtsStart);
    return cue.sii;
}

void RAPP::StopSounds(CTG ctgDev, long sii, long sqn, long scl)
{
    CUE cue;
    long icue;
    ulong tsNow = _DtsOut();

    if (pvNil == _pglcue)
        return;
    for (icue = 0; icue < _pglcue->IvMac(); icue++)
    {
        _pglcue->Get(icue, &cue);
        if (cue.ctgDev != ctgDev || cue.tsEnd <= tsNow)
            continue;
        if (sii != siiNil && cue.sii != sii)
            continue;
        if (sqn != sqnNil && cue.sqn != sqn)
            continue;
        if (scl != sclNil && cue.scl != scl)
            continue;
        cue.tsEnd = LwMax(cue.tsStart, tsNow);
        _pglcue->Put(icue, &cue);
    }
}

bool RAPP::FSoundsPlaying(CTG ctgDev, long sii, long sqn, long scl)
{
    CUE cue;
    long icue;
    ulong tsNow = _DtsOut();

    if (pvNil == _pglcue)
        return fFalse;
    for (icue = 0; icue < _pglcue->IvMac(); icue++)
    {
        _pglcue->Get(icue, &cue);
        if (cue.ctgDev != ctgDev || cue.tsEnd <= tsNow)
            continue;
        if (sii != siiNil && cue.sii != sii)
            continue;
        if (sqn != sqnNil && cue.sqn != sqn)
            continue;
        if (scl != sclNil && cue.scl != scl)
            continue;
        return fTrue;
    }
    return fFalse;
}

/***************************************************************************
    Write a sound chunk out as a standard file: WAVE chunks already are
    RIFF files; MIDS chunks are re-encoded as a type-0 MIDI file with one
    tick per millisecond.
***************************************************************************/
static void _PutBe(FILE *pfile, ulong lu, long cb)
{
    while (cb-- > 0)
        fputc((int)((lu >> (8 * cb)) & 0xFF), pfile);
}

static void _PutVar(FILE *pfile, ulong lu)
{
    byte rgb[5];
    long cb = 0;

    rgb[cb++] = (byte)(lu & 0x7F);
    while ((lu >>= 7) != 0)
        rgb[cb++] = (byte)((lu & 0x7F) | 0x80);
    while (cb-- > 0)
        fputc(rgb[cb], pfile);
}

bool RAPP::_FWriteSoundFile(SNDF *psndf, long isndf)
{
    char szPath[MAX_PATH];
    FILE *pfile;
    BLCK blck;
    long cb;
    byte *prgb;

    if (psndf->ctg == kctgWave)
    {
        _snprintf(szPath, MAX_PATH, "%s\\sounds\\s%03ld.wav", _stnOutDir.Psz(), isndf);
        if (!psndf->pcrf->Pcfl()->FFind(psndf->ctg, psndf->cno, &blck) || !blck.FUnpackData())
            return fFalse;
        cb = blck.Cb();
        if (cb <= 0 || pvNil == (prgb = (byte *)malloc(cb)))
            return fFalse;
        if (!blck.FReadRgb(prgb, cb, 0) || pvNil == (pfile = fopen(szPath, "wb")))
        {
            free(prgb);
            return fFalse;
        }
        fwrite(prgb, 1, cb, pfile);
        fclose(pfile);

        // length: walk the RIFF chunks for fmt (byte rate) and data (size)
        if (cb > 12 && 0 == memcmp(prgb, "RIFF", 4) && 0 == memcmp(prgb + 8, "WAVE", 4))
        {
            long ib = 12;
            ulong cbPerSec = 0, cbData = 0;
            while (ib + 8 <= cb)
            {
                ulong cbChunk = *(ulong *)(prgb + ib + 4);
                if (0 == memcmp(prgb + ib, "fmt ", 4) && ib + 16 <= cb)
                    cbPerSec = *(ulong *)(prgb + ib + 8 + 8);
                else if (0 == memcmp(prgb + ib, "data", 4))
                    cbData = cbChunk;
                ib += 8 + cbChunk + (cbChunk & 1);
            }
            if (cbPerSec > 0)
                psndf->dtsLen = (ulong)((double)cbData * 1000.0 / cbPerSec);
        }
        free(prgb);
        return fTrue;
    }

    if (psndf->ctg == kctgMidi)
    {
        PMIDS pmids;
        MSTP mstp;
        MIDEV midev;
        ulong tsLast = 0;
        long lwTrackLenPos, lwTrackStart, lwEnd;

        _snprintf(szPath, MAX_PATH, "%s\\sounds\\s%03ld.mid", _stnOutDir.Psz(), isndf);
        pmids = (PMIDS)psndf->pcrf->PbacoFetch(psndf->ctg, psndf->cno, MIDS::FReadMids);
        if (pvNil == pmids)
            return fFalse;
        if (pvNil == (pfile = fopen(szPath, "wb")))
        {
            ReleasePpo(&pmids);
            return fFalse;
        }
        fwrite("MThd", 1, 4, pfile);
        _PutBe(pfile, 6, 4);
        _PutBe(pfile, 0, 2);    // format 0
        _PutBe(pfile, 1, 2);    // one track
        _PutBe(pfile, 1000, 2); // 1000 ticks per quarter...
        fwrite("MTrk", 1, 4, pfile);
        lwTrackLenPos = ftell(pfile);
        _PutBe(pfile, 0, 4);
        lwTrackStart = ftell(pfile);
        // ...at one quarter per second, so a tick is a millisecond
        _PutVar(pfile, 0);
        fputc(0xFF, pfile);
        fputc(0x51, pfile);
        fputc(0x03, pfile);
        _PutBe(pfile, 1000000, 3);

        mstp.Init(pmids, 0, 500000);
        while (mstp.FGetEvent(&midev))
        {
            if (midev.cb <= 0 || midev.rgbSend[0] < 0x80 || midev.rgbSend[0] >= 0xF0)
                continue; // tempo marker, or nothing a synth needs
            _PutVar(pfile, midev.ts - tsLast);
            fwrite(midev.rgbSend, 1, midev.cb, pfile);
            tsLast = midev.ts;
        }
        _PutVar(pfile, 0);
        fputc(0xFF, pfile);
        fputc(0x2F, pfile);
        fputc(0x00, pfile);
        lwEnd = ftell(pfile);
        fseek(pfile, lwTrackLenPos, SEEK_SET);
        _PutBe(pfile, lwEnd - lwTrackStart, 4);
        fclose(pfile);
        ReleasePpo(&pmids);
        psndf->dtsLen = tsLast;
        return fTrue;
    }
    return fFalse;
}

/***************************************************************************
    Write audio.ffscript: an ffmpeg filtergraph that rebuilds the
    soundtrack from the extracted sounds (MIDI files are expected to have
    been rendered to sNNN.mid.wav first). Run from the output folder:
        ffmpeg -filter_complex_script audio.ffscript -map [aout] audio.wav
***************************************************************************/
void RAPP::_WriteAudioScript(ulong dtsEnd)
{
    char szPath[MAX_PATH];
    FILE *pfile;
    CUE cue;
    SNDF sndf;
    VLMEV vlmev;
    long icue, ccue = 0, ivlmev;

    if (pvNil == _pglcue || pvNil == _pglsndf)
        return;

    _snprintf(szPath, MAX_PATH, "%s\\audio.ffscript", _stnOutDir.Psz());
    if (pvNil == (pfile = fopen(szPath, "w")))
        return;

    // a silent bed exactly as long as the movie anchors the mix at t=0
    fprintf(pfile, "anullsrc=r=44100:cl=stereo,atrim=duration=%.3f,aformat=sample_fmts=fltp[base];\n", dtsEnd / 1000.0);

    for (icue = 0; icue < _pglcue->IvMac(); icue++)
    {
        ulong tsEnd, dtsPlay;
        long cloop;

        _pglcue->Get(icue, &cue);
        _pglsndf->Get(cue.isndf, &sndf);
        tsEnd = LwMin(cue.tsEnd, dtsEnd);
        if (tsEnd <= cue.tsStart || cue.tsStart >= dtsEnd)
            continue;
        dtsPlay = tsEnd - cue.tsStart;

        // ffmpeg can't trim an endless loop, so ask for just enough loops
        if (cue.cactPlay > 0 && cue.cactPlay < kcactLoopForever)
            cloop = cue.cactPlay;
        else if (sndf.dtsLen > 0)
            cloop = (long)((cue.dtsOffset + dtsPlay) / sndf.dtsLen) + 1;
        else
            cloop = 1;

        fprintf(pfile,
                "amovie='sounds/s%03ld.%s':loop=%ld,atrim=start=%.3f:duration=%.3f,asetpts=PTS-STARTPTS,"
                "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=%.4f,"
                "adelay=delays=%lu:all=1[a%ld];\n",
                cue.isndf, sndf.ctg == kctgMidi ? "mid.wav" : "wav", cloop, cue.dtsOffset / 1000.0, dtsPlay / 1000.0,
                (double)cue.vlm / kvlmFull, cue.tsStart, ccue);
        ccue++;
    }

    fprintf(pfile, "[base]");
    for (icue = 0; icue < ccue; icue++)
        fprintf(pfile, "[a%ld]", icue);
    fprintf(pfile, "amix=inputs=%ld:normalize=0:duration=first", ccue + 1);

    // master volume envelope (the end-of-movie fade)
    if (_pglvlmev->IvMac() > 0)
    {
        fprintf(pfile, ",volume='");
        for (ivlmev = 0; ivlmev < _pglvlmev->IvMac(); ivlmev++)
        {
            _pglvlmev->Get(ivlmev, &vlmev);
            fprintf(pfile, "if(lt(t,%.3f),%.4f,", vlmev.ts / 1000.0,
                    ivlmev == 0 ? 1.0 : (double)((VLMEV *)_pglvlmev->QvGet(ivlmev - 1))->vlm / kvlmFull);
        }
        fprintf(pfile, "%.4f", (double)vlmev.vlm / kvlmFull);
        for (ivlmev = 0; ivlmev < _pglvlmev->IvMac(); ivlmev++)
            fputc(')', pfile);
        fprintf(pfile, "':eval=frame");
    }
    fprintf(pfile, "[aout]\n");
    fclose(pfile);
    _Log("audio: %ld sounds, %ld cues", _pglsndf->IvMac(), ccue);
}
