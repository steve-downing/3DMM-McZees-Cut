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

    --smooth adds three in-between frames for every 6 fps step in which
    only actors moved: every actor part's transform is blended between the
    two frames, so motion plays at 24 fps.

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
#include <math.h>
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
    _dtsEndHold = 3 * kdtsSecond; // 3DMM leaves the last frame up; give it time to be read
    _cfrmLimit = 0;
    _fStereo = fFalse;
    _pctDepth = 2.5;
    _pctPop = 1.5;
    _fDebug = fFalse;
    _fSmooth = fFalse;
    _prgsnapPrev = pvNil;
    _prgsnapCur = pvNil;
    _csnapPrev = _csnapCur = _csnapMax = 0;
    _fSnapPrevValid = fFalse;
    _dtsPrevEmit = 0;
    _cblendDone = _cblendHeld = 0;
    _fStereoValid = fFalse;
    _luTboxSig = 0;
    _pgstMissingFonts = pvNil;
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
    _LoadFonts();
    vpfnMissingFont = RAPP::_MissingFont;
    if (!RAPP_PAR::_FInit(grfapp, grfgob, ginDef))
    {
        _Log("framework init failed");
        _lwExit = klwExitInit;
        return fFalse;
    }
    _Log("fonts: %ld TrueType faces available", vntl.OnnMac());
    if (_fDebug)
    {
        long onn;
        STN stn;
        for (onn = 0; onn < vntl.OnnMac(); onn++)
        {
            vntl.GetStn(onn, &stn);
            _Log("font: %s", stn.Psz());
        }
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
        else if (0 == strcmp(psz, "--fonts") && iarg + 1 < __argc)
            _stnFonts.SetSz(__argv[++iarg]);
        else if (0 == strcmp(psz, "--end-hold") && iarg + 1 < __argc)
            _dtsEndHold = (ulong)(atof(__argv[++iarg]) * kdtsSecond);
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
        else if (0 == strcmp(psz, "--smooth"))
            _fSmooth = fTrue;
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
                        "[--fonts <dir>] [--end-hold <sec>] [--max-frames <n>] [--stereo] [--depth <percent>] [--pop "
                        "<percent>] [--smooth] [--debug]\n");
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
    if (_fSmooth)
        _Log("smooth: on (three blended frames between 3DMM's, 24 fps)");
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
    if (_fSmooth)
    {
        _csnapMax = 4096;
        _prgsnapPrev = (SNAPA *)malloc(_csnapMax * size(SNAPA));
        _prgsnapCur = (SNAPA *)malloc(_csnapMax * size(SNAPA));
        if (pvNil == _prgsnapPrev || pvNil == _prgsnapCur)
            return fFalse;
    }
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
    _FinishTimeline(_DtsOut() + _dtsEndHold);
    _WriteAudioScript(_DtsOut() + _dtsEndHold);
    _WriteSoundIndex();
    _Event("end");
    if (_fSmooth)
        _Log("smooth: %ld steps blended, %ld held (more than actor poses changed)", _cblendDone, _cblendHeld);
    _Log("done: %ld frames, %.2f seconds", _cfrmOut, _DtsOut() / 1000.0);
    return _lwExit == klwExitOk;
}

/***************************************************************************
    Run everything that's due: OS messages (the hidden window), then
    the command queue, which is where clock alarms and the movie's
    per-frame render commands are delivered.

    Like APPB::_Loop, marked regions are flushed before every command
    (APPB::TopOfLoop). Playback depends on this in three ways:
      - a frame goes on screen as soon as the scene advances to it; its
        sounds start with the next frame command
      - a scene transition runs as soon as the scene switches, so the new
        scene's sounds start after the dissolve, not during it
      - scrolling credits only redraw this way, between frame commands
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
    for (ccmd = 0; ccmd < kccmdMaxPerTick; ccmd++)
    {
        if (pvNil != _pglmkrgn && _pglmkrgn->IvMac() > 0)
            UpdateMarked();
        if (!vpcex->FDispatchNextCmd())
            break;
    }
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
    Draw the movie view into _prgbCur: once for mono; for stereo, once per
    eye plus once more from the real camera, so 2-D output made from a
    stereo render is exactly what 3DMM showed.
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

    // the plain 2-D view
    pbwld->Render();
    pmvu->DrawTree(_pgptCapture, pvNil, pvNil, fgobNil);
    _ConvertCapture(_prgbEye);
    _PlaceEye(_prgbEye, _prgbCur, 2, 0);

    // Stereo parameters are chosen once per camera view, from its first
    // frame, so depth doesn't "breathe" as actors move around.
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
    _PlaceEye(_prgbEye, _prgbCur, 2, 0);
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
    bool fSnap = fFalse;

    if (pvNil == _pmvie || pvNil == _pgptCapture || pvNil == (pmvu = _pmvie->PmvuCur()))
        return;

    // Animated transitions are synthesized below rather than run, so
    // clear the request before anything tries to animate it.
    trans = _pmvie->Trans();
    if (trans != transNil)
        _pmvie->SetTrans(transNil);

    _UpdatePalette();
    _DrawFrame(pmvu);
    _LogTextBoxes();
    if (trans == transBlack)
        ClearPb(_prgbCur, cb);

    if (_fHavePrev && trans == transNil && FEqualRgb(_prgbPrev, _prgbCur, cb))
        return;

    dtsOut = _DtsOut();
    if (_fSmooth)
    {
        PBWLD pbwld = _pmvie->Pbwld();
        fSnap = pvNil != _pmvie->Pscen() && pvNil != pbwld && _FSnapshot(pbwld, _prgsnapCur, &_csnapCur);
        if (fSnap && _fHavePrev && _fSnapPrevValid && trans == transNil)
            _EmitInBetweens(pmvu, dtsOut);
    }
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

    if (_fSmooth)
    {
        // what's on screen now is the starting point for the next in-betweens
        SNAPA *prgsnapT = _prgsnapPrev;
        _ReleaseSnapshot(_prgsnapPrev, &_csnapPrev);
        _prgsnapPrev = _prgsnapCur;
        _csnapPrev = _csnapCur;
        _prgsnapCur = prgsnapT;
        _csnapCur = 0;
        _fSnapPrevValid = fSnap;
        _dtsPrevEmit = dtsOut;
    }
}

/***************************************************************************
    --smooth. 3DMM moves everything at 6 frames a second. Between two
    frames that differ only in where things are and which model each
    actor part shows, draw three more: each BRender actor's transform
    blended between the two frames, and models switched halfway. Blending
    happens in position / rotation (slerp) / scale, plus whatever the
    matrix holds beyond those (shear in squash-and-stretch cels), so the
    blend lands exactly on both frames.

    Before drawing in-betweens, the earlier frame is redrawn from its
    saved transforms; unless that matches what was shown, something
    other than actor transforms changed (a camera cut, text, a costume,
    an actor arriving), and the interval is left as it was.
***************************************************************************/
struct XFD
{
    double p[3], q[4], s[3], rgres[12];
};

static void _MatFromXfd(const double *pp, const double *pq, const double *ps, double rgm[12])
{
    double x = pq[0], y = pq[1], z = pq[2], w = pq[3];
    double rgr[3][3] = {{1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)},
                        {2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)},
                        {2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)}};
    long i, j;

    // BRender rows are the transformed axes: row j = column j of R, times scale j
    for (j = 0; j < 3; j++)
        for (i = 0; i < 3; i++)
            rgm[j * 3 + i] = rgr[i][j] * ps[j];
    for (i = 0; i < 3; i++)
        rgm[9 + i] = pp[i];
}

static void _Decompose(br_matrix34 *pbmat, XFD *pxfd)
{
    double rgm[12], rgr[3][3], rgmT[12];
    double det, tr, s;
    long i, j;

    for (j = 0; j < 4; j++)
        for (i = 0; i < 3; i++)
            rgm[j * 3 + i] = BrScalarToFloat(pbmat->m[j][i]);
    for (j = 0; j < 3; j++)
        pxfd->s[j] = sqrt(rgm[j * 3] * rgm[j * 3] + rgm[j * 3 + 1] * rgm[j * 3 + 1] + rgm[j * 3 + 2] * rgm[j * 3 + 2]);
    det = rgm[0] * (rgm[4] * rgm[8] - rgm[5] * rgm[7]) - rgm[1] * (rgm[3] * rgm[8] - rgm[5] * rgm[6]) +
          rgm[2] * (rgm[3] * rgm[7] - rgm[4] * rgm[6]);
    if (det < 0)
        pxfd->s[0] = -pxfd->s[0];
    for (j = 0; j < 3; j++)
        for (i = 0; i < 3; i++)
            rgr[i][j] = pxfd->s[j] != 0 ? rgm[j * 3 + i] / pxfd->s[j] : (i == j);
    tr = rgr[0][0] + rgr[1][1] + rgr[2][2];
    if (tr > 0)
    {
        s = 0.5 / sqrt(tr + 1);
        pxfd->q[3] = 0.25 / s;
        pxfd->q[0] = (rgr[2][1] - rgr[1][2]) * s;
        pxfd->q[1] = (rgr[0][2] - rgr[2][0]) * s;
        pxfd->q[2] = (rgr[1][0] - rgr[0][1]) * s;
    }
    else if (rgr[0][0] > rgr[1][1] && rgr[0][0] > rgr[2][2])
    {
        s = 2 * sqrt(1 + rgr[0][0] - rgr[1][1] - rgr[2][2]);
        pxfd->q[3] = (rgr[2][1] - rgr[1][2]) / s;
        pxfd->q[0] = 0.25 * s;
        pxfd->q[1] = (rgr[0][1] + rgr[1][0]) / s;
        pxfd->q[2] = (rgr[0][2] + rgr[2][0]) / s;
    }
    else if (rgr[1][1] > rgr[2][2])
    {
        s = 2 * sqrt(1 + rgr[1][1] - rgr[0][0] - rgr[2][2]);
        pxfd->q[3] = (rgr[0][2] - rgr[2][0]) / s;
        pxfd->q[0] = (rgr[0][1] + rgr[1][0]) / s;
        pxfd->q[1] = 0.25 * s;
        pxfd->q[2] = (rgr[1][2] + rgr[2][1]) / s;
    }
    else
    {
        s = 2 * sqrt(1 + rgr[2][2] - rgr[0][0] - rgr[1][1]);
        pxfd->q[3] = (rgr[1][0] - rgr[0][1]) / s;
        pxfd->q[0] = (rgr[0][2] + rgr[2][0]) / s;
        pxfd->q[1] = (rgr[1][2] + rgr[2][1]) / s;
        pxfd->q[2] = 0.25 * s;
    }
    s = sqrt(pxfd->q[0] * pxfd->q[0] + pxfd->q[1] * pxfd->q[1] + pxfd->q[2] * pxfd->q[2] + pxfd->q[3] * pxfd->q[3]);
    for (i = 0; i < 4; i++)
        pxfd->q[i] = s > 0 ? pxfd->q[i] / s : (i == 3);
    for (i = 0; i < 3; i++)
        pxfd->p[i] = rgm[9 + i];
    _MatFromXfd(pxfd->p, pxfd->q, pxfd->s, rgmT);
    for (i = 0; i < 12; i++)
        pxfd->rgres[i] = rgm[i] - rgmT[i];
}

// blend two transforms; false if the turn between them is too big to blend
static bool _FBlend(br_matrix34 *pbmatA, br_matrix34 *pbmatB, double t, br_matrix34 *pbmatOut)
{
    XFD xa, xb;
    double p[3], q[4], s[3], rgm[12], dot, ang, wa, wb, sn;
    long i, j;

    _Decompose(pbmatA, &xa);
    _Decompose(pbmatB, &xb);
    dot = xa.q[0] * xb.q[0] + xa.q[1] * xb.q[1] + xa.q[2] * xb.q[2] + xa.q[3] * xb.q[3];
    if (dot < 0)
    {
        dot = -dot;
        for (i = 0; i < 4; i++)
            xb.q[i] = -xb.q[i];
    }
    if (dot > 1)
        dot = 1;
    ang = acos(dot); // half the turn
    if (2 * ang > 2.0)
        return fFalse; // over ~115 degrees: a flip, not a motion
    if (ang < 1e-6)
        wa = 1 - t, wb = t;
    else
    {
        sn = sin(ang);
        wa = sin((1 - t) * ang) / sn;
        wb = sin(t * ang) / sn;
    }
    for (i = 0; i < 4; i++)
        q[i] = wa * xa.q[i] + wb * xb.q[i];
    for (i = 0; i < 3; i++)
    {
        p[i] = xa.p[i] + (xb.p[i] - xa.p[i]) * t;
        s[i] = xa.s[i] + (xb.s[i] - xa.s[i]) * t;
    }
    _MatFromXfd(p, q, s, rgm);
    for (j = 0; j < 4; j++)
        for (i = 0; i < 3; i++)
            pbmatOut->m[j][i] =
                BrFloatToScalar(rgm[j * 3 + i] + (1 - t) * xa.rgres[j * 3 + i] + t * xb.rgres[j * 3 + i]);
    return fTrue;
}

bool RAPP::_FSnapshot(PBWLD pbwld, SNAPA *prgsnap, long *pcsnap)
{
    BACT *rgpbactStack[512];
    long cpbact = 0;
    BACT *pbact;

    _ReleaseSnapshot(prgsnap, pcsnap);
    if (pvNil == pbwld)
        return fFalse;
    for (pbact = pbwld->PbactWorld()->children; pvNil != pbact; pbact = pbact->next)
        rgpbactStack[cpbact++] = pbact;
    while (cpbact > 0)
    {
        pbact = rgpbactStack[--cpbact];
        if (*pcsnap >= _csnapMax)
            return fFalse;
        prgsnap[*pcsnap].pbact = pbact;
        prgsnap[*pcsnap].t = pbact->t;
        prgsnap[*pcsnap].pbmdl = pbact->model;
        if (pvNil != pbact->model)
            MODL::PmodlFromBmdl(pbact->model)->AddRef();
        (*pcsnap)++;
        for (BACT *pbactKid = pbact->children; pvNil != pbactKid; pbactKid = pbactKid->next)
        {
            if (cpbact >= 512)
                return fFalse;
            rgpbactStack[cpbact++] = pbactKid;
        }
    }
    return fTrue;
}

void RAPP::_ReleaseSnapshot(SNAPA *prgsnap, long *pcsnap)
{
    long isnap;

    for (isnap = 0; isnap < *pcsnap; isnap++)
    {
        if (pvNil != prgsnap[isnap].pbmdl)
        {
            PMODL pmodl = MODL::PmodlFromBmdl(prgsnap[isnap].pbmdl);
            ReleasePpo(&pmodl);
        }
    }
    *pcsnap = 0;
}

/***************************************************************************
    Pose every actor a fraction t of the way from the shown frame
    (_prgsnapPrev) to the coming one (_prgsnapCur). t = 0 restores the
    shown frame exactly; t = 1 the coming one. Actors that only exist in
    the coming frame stay as they are.
***************************************************************************/
void RAPP::_PoseBetween(double t)
{
    long isnap, jsnap;

    for (isnap = 0; isnap < _csnapCur; isnap++)
    {
        SNAPA *psnapB = &_prgsnapCur[isnap], *psnapA = pvNil;
        BACT *pbact = psnapB->pbact;

        for (jsnap = 0; jsnap < _csnapPrev; jsnap++)
        {
            if (_prgsnapPrev[jsnap].pbact == pbact)
            {
                psnapA = &_prgsnapPrev[jsnap];
                break;
            }
        }
        if (pvNil == psnapA || t >= 1)
        {
            pbact->t = psnapB->t;
            pbact->model = psnapB->pbmdl;
            continue;
        }
        pbact->model = (t < 0.5) ? psnapA->pbmdl : psnapB->pbmdl;
        if (t <= 0)
            pbact->t = psnapA->t;
        else if (psnapA->t.type != BR_TRANSFORM_MATRIX34 || psnapB->t.type != BR_TRANSFORM_MATRIX34 ||
                 FEqualRgb(&psnapA->t, &psnapB->t, size(br_transform)))
            pbact->t = (t < 0.5) ? psnapA->t : psnapB->t;
        else
        {
            pbact->t = psnapB->t;
            if (!_FBlend(&psnapA->t.t.mat, &psnapB->t.t.mat, t, &pbact->t.t.mat))
                pbact->t = (t < 0.5) ? psnapA->t : psnapB->t;
        }
    }
}

void RAPP::_RenderInto(PMVU pmvu, byte *prgb)
{
    PBWLD pbwld = _pmvie->Pbwld();
    byte *prgbSave = _prgbCur;

    pbwld->MarkDirty();
    pbwld->Render();
    _prgbCur = prgb;
    _DrawFrame(pmvu);
    _prgbCur = prgbSave;
}

void RAPP::_EmitInBetweens(PMVU pmvu, ulong dtsOut)
{
    long cb = _DxpOut() * kdypRender * 3;
    ulong dts = dtsOut - _dtsPrevEmit;
    long k;

    // only across one ordinary 6 fps step; held frames stay held
    if (dts < kdtsSecond / 10 || dts > kdtsSecond / 4)
        return;

    _PoseBetween(0);
    _RenderInto(pmvu, _prgbScratch);
    if (FEqualRgb(_prgbScratch, _prgbPrev, cb))
    {
        for (k = 1; k < 4; k++)
        {
            _PoseBetween(k / 4.0);
            _RenderInto(pmvu, _prgbScratch);
            _FEmitFrame(_prgbScratch, _dtsPrevEmit + LwMulDiv(k, dts, 4));
        }
        _cblendDone++;
    }
    else
        _cblendHeld++;

    // back to the coming frame, and leave the world drawn that way
    _PoseBetween(1);
    _pmvie->Pbwld()->MarkDirty();
    _pmvie->Pbwld()->Render();
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
    long cbRow = dxp * 3; // 544 and 1632 are multiples of 4
    long cbImage = cbRow * kdypRender;
    long cbFile = size(rgbHeader) + cbImage;
    long yp, xp;
    byte rgbRow[3 * kdxpRender * 3];

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
        _FinishTimeline(_DtsOut() + _dtsEndHold);
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
        _DescribeSound(&sndf);
        sndf.fPlayed = fTrue;
        sndf.tsFirst = tsNow;
        sndf.iscen = -1;
        sndf.nfrm = 0;
        if (pvNil != _pmvie && pvNil != _pmvie->Pscen())
        {
            sndf.iscen = _pmvie->Iscen();
            sndf.nfrm = _pmvie->Pscen()->Nfrm() - _pmvie->Pscen()->NfrmFirst() + 1;
        }
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
    _WriteAudioCues(dtsEnd);
}

/***************************************************************************
    audio-cues.tsv: the same cues as audio.ffscript, with each sound's
    category (from the queue number MSND gives it: speech, effects,
    music) and owner, so the encoder can level and route them.
    audio-master.tsv: master volume changes.
***************************************************************************/
void RAPP::_WriteAudioCues(ulong dtsEnd)
{
    char szPath[MAX_PATH];
    FILE *pfile;
    CUE cue;
    SNDF sndf;
    VLMEV vlmev;
    long icue, ivlmev;

    _snprintf(szPath, MAX_PATH, "%s\\audio-cues.tsv", _stnOutDir.Psz());
    if (pvNil == (pfile = fopen(szPath, "w")))
        return;
    fprintf(pfile, "# duration\t%.3f\n", dtsEnd / 1000.0);
    fprintf(pfile, "file\tcategory\towner\tobject\tstart\tduration\toffset\tloops\tvolume\tlength\n");
    for (icue = 0; icue < _pglcue->IvMac(); icue++)
    {
        ulong tsEnd, dtsPlay;
        long cloop, sty, grfOwner;
        PSZ pszCategory, pszOwner;

        _pglcue->Get(icue, &cue);
        _pglsndf->Get(cue.isndf, &sndf);
        tsEnd = LwMin(cue.tsEnd, dtsEnd);
        if (tsEnd <= cue.tsStart || cue.tsStart >= dtsEnd)
            continue;
        dtsPlay = tsEnd - cue.tsStart;
        if (cue.cactPlay > 0 && cue.cactPlay < kcactLoopForever)
            cloop = cue.cactPlay;
        else if (sndf.dtsLen > 0)
            cloop = (long)((cue.dtsOffset + dtsPlay) / sndf.dtsLen) + 1;
        else
            cloop = 1;

        // MSND queue numbers: owner bits | sty << ksqnStyShift | object id
        sty = (cue.sqn >> 16) & 0xFFF;
        grfOwner = cue.sqn & 0x30000000;
        if (sndf.ctg == kctgMidi || sty == styMidi)
            pszCategory = PszLit("music");
        else if (sty == stySpeech)
            pszCategory = PszLit("speech");
        else
            pszCategory = PszLit("sfx");
        pszOwner = (grfOwner == sqnActr) ? PszLit("actor") : (grfOwner == sqnBkgd ? PszLit("scene") : PszLit("none"));

        fprintf(pfile, "sounds/s%03ld.%s\t%s\t%s\t%ld\t%.3f\t%.3f\t%.3f\t%ld\t%.4f\t%.3f\n", cue.isndf,
                sndf.ctg == kctgMidi ? "mid.wav" : "wav", pszCategory, pszOwner, cue.sqn & 0xFFFF, cue.tsStart / 1000.0,
                dtsPlay / 1000.0, cue.dtsOffset / 1000.0, cloop, (double)cue.vlm / kvlmFull, sndf.dtsLen / 1000.0);
    }
    fclose(pfile);

    _snprintf(szPath, MAX_PATH, "%s\\audio-master.tsv", _stnOutDir.Psz());
    if (pvNil == (pfile = fopen(szPath, "w")))
        return;
    fprintf(pfile, "time\tvolume\n");
    for (ivlmev = 0; ivlmev < _pglvlmev->IvMac(); ivlmev++)
    {
        _pglvlmev->Get(ivlmev, &vlmev);
        fprintf(pfile, "%.3f\t%.4f\n", vlmev.ts / 1000.0, (double)vlmev.vlm / kvlmFull);
    }
    fclose(pfile);
}

/***************************************************************************
    Fill in a sound's MSND (for its name and kind) and whether it lives in
    the movie or in 3DMM's content.
***************************************************************************/
void RAPP::_DescribeSound(SNDF *psndf)
{
    PCFL pcfl = psndf->pcrf->Pcfl();
    PCRF pcrfMovie = (pvNil != _pmvie) ? _pmvie->PcrfAutoSave() : pvNil;
    CKI cki;
    KID kid;
    long icki, ikid;
    bool fInvalid;

    psndf->cnoMsnd = cnoNil;
    psndf->sty = (psndf->ctg == kctgMidi) ? styMidi : stySfx;
    psndf->fMovie = pvNil != pcrfMovie && pcfl == pcrfMovie->Pcfl();
    for (icki = 0; pcfl->FGetCkiCtg(kctgMsnd, icki, &cki); icki++)
    {
        for (ikid = 0; pcfl->FGetKid(kctgMsnd, cki.cno, ikid, &kid); ikid++)
        {
            if (kid.cki.ctg == psndf->ctg && kid.cki.cno == psndf->cno)
            {
                psndf->cnoMsnd = cki.cno;
                if (!MSND::FGetMsndInfo(pcfl, kctgMsnd, cki.cno, &fInvalid, &psndf->sty))
                    psndf->sty = (psndf->ctg == kctgMidi) ? styMidi : stySfx;
                return;
            }
        }
    }
}

/***************************************************************************
    sounds\index.tsv: every extracted sound, with its name, kind, where it
    comes from and where the movie first plays it. Sounds stored in the
    movie that it never plays are extracted too, so nothing is lost.
***************************************************************************/
void RAPP::_WriteSoundIndex(void)
{
    PCRF pcrfMovie = (pvNil != _pmvie) ? _pmvie->PcrfAutoSave() : pvNil;
    char szPath[MAX_PATH];
    FILE *pfile;
    SNDF sndf, sndfT;
    CKI cki;
    KID kid;
    STN stn;
    long icki, ikid, isndf;
    bool fInvalid;
    long sty;

    if (pvNil == _pglsndf)
        return;

    // never-played sounds stored in the movie
    if (pvNil != pcrfMovie)
    {
        PCFL pcfl = pcrfMovie->Pcfl();
        for (icki = 0; pcfl->FGetCkiCtg(kctgMsnd, icki, &cki); icki++)
        {
            if (!MSND::FGetMsndInfo(pcfl, kctgMsnd, cki.cno, &fInvalid, &sty) || fInvalid)
                continue;
            for (ikid = 0; pcfl->FGetKid(kctgMsnd, cki.cno, ikid, &kid); ikid++)
            {
                if (kid.cki.ctg != kctgWave && kid.cki.ctg != kctgMidi)
                    continue;
                for (isndf = 0; isndf < _pglsndf->IvMac(); isndf++)
                {
                    _pglsndf->Get(isndf, &sndfT);
                    if (sndfT.fMovie && sndfT.ctg == kid.cki.ctg && sndfT.cno == kid.cki.cno)
                        break;
                }
                if (isndf < _pglsndf->IvMac())
                    continue;
                ClearPb(&sndf, size(sndf));
                sndf.pcrf = pcrfMovie;
                sndf.ctg = kid.cki.ctg;
                sndf.cno = kid.cki.cno;
                sndf.cnoMsnd = cki.cno;
                sndf.sty = sty;
                sndf.fMovie = fTrue;
                sndf.fPlayed = fFalse;
                if (_FWriteSoundFile(&sndf, isndf) && _pglsndf->FAdd(&sndf))
                    _Event("unused-sound s%03ld", isndf);
            }
        }
    }

    _snprintf(szPath, MAX_PATH, "%s\\sounds\\index.tsv", _stnOutDir.Psz());
    if (pvNil == (pfile = fopen(szPath, "w")))
        return;
    fprintf(pfile, "# file\tfirst\tscene\tframe\tcategory\tsource\tname\n");
    for (isndf = 0; isndf < _pglsndf->IvMac(); isndf++)
    {
        PSZ pszCategory;
        long ich;

        _pglsndf->Get(isndf, &sndf);
        stn.SetNil();
        if (cnoNil != sndf.cnoMsnd)
            sndf.pcrf->Pcfl()->FGetName(kctgMsnd, sndf.cnoMsnd, &stn);
        for (ich = 0; ich < stn.Cch(); ich++)
        {
            if ((byte)stn.Psz()[ich] < ' ')
                stn.Psz()[ich] = ' ';
        }
        if (sndf.ctg == kctgMidi || sndf.sty == styMidi)
            pszCategory = PszLit("music");
        else if (sndf.sty == stySpeech)
            pszCategory = PszLit("speech");
        else
            pszCategory = PszLit("sfx");
        if (sndf.fPlayed)
            fprintf(pfile, "s%03ld.%s\t%.3f\t%ld\t%ld\t%s\t%s\t%s\n", isndf, sndf.ctg == kctgMidi ? "mid" : "wav",
                    sndf.tsFirst / 1000.0, sndf.iscen + 1, sndf.nfrm, pszCategory, sndf.fMovie ? "movie" : "library",
                    stn.Psz());
        else
            fprintf(pfile, "s%03ld.%s\t\t\t\t%s\t%s\t%s\n", isndf, sndf.ctg == kctgMidi ? "mid" : "wav", pszCategory,
                    sndf.fMovie ? "movie" : "library", stn.Psz());
    }
    fclose(pfile);
}

/***************************************************************************
    Note when the set of visible 2-D text boxes changes, with a snippet of
    each one's text, so they can be found on the timeline.
***************************************************************************/
void RAPP::_LogTextBoxes(void)
{
    PSCEN pscen = _pmvie->Pscen();
    PTBOX ptbox;
    long itbox, ccp, ich;
    ulong luSig = 0;
    achar rgch[41];

    if (pvNil == pscen)
        return;
    for (itbox = 0; pvNil != (ptbox = pscen->PtboxFromItbox(itbox)); itbox++)
    {
        if (ptbox->FIsVisible())
            luSig = luSig * 31 + (ulong)ptbox + 1;
    }
    if (luSig == _luTboxSig)
        return;
    _luTboxSig = luSig;

    for (itbox = 0; pvNil != (ptbox = pscen->PtboxFromItbox(itbox)); itbox++)
    {
        if (!ptbox->FIsVisible())
            continue;
        ccp = LwMin(ptbox->CpMac(), 40);
        ptbox->FetchRgch(0, ccp, rgch);
        for (ich = 0; ich < ccp; ich++)
        {
            if ((byte)rgch[ich] < ' ')
                rgch[ich] = ' ';
        }
        rgch[ccp] = 0;
        _Event("textbox %s \"%s\"", ptbox->FStory() ? "story" : "credits", rgch);
    }
}

/***************************************************************************
    --fonts: make every font file in a folder available to this process
    only (nothing gets installed), before the font list is built.
***************************************************************************/
void RAPP::_LoadFonts(void)
{
    static const char *const rgszPattern[] = {"*.ttf", "*.ttc", "*.otf", "*.fon", "*.fnt"};
    char szPattern[MAX_PATH], szFile[MAX_PATH];
    WIN32_FIND_DATAA wfd;
    HANDLE hfind;
    long isz, cfont = 0;

    if (_stnFonts.Cch() == 0)
        return;
    for (isz = 0; isz < (long)(sizeof(rgszPattern) / sizeof(rgszPattern[0])); isz++)
    {
        _snprintf(szPattern, MAX_PATH, "%s\\%s", _stnFonts.Psz(), rgszPattern[isz]);
        if (INVALID_HANDLE_VALUE == (hfind = FindFirstFileA(szPattern, &wfd)))
            continue;
        do
        {
            _snprintf(szFile, MAX_PATH, "%s\\%s", _stnFonts.Psz(), wfd.cFileName);
            if (AddFontResourceExA(szFile, FR_PRIVATE, 0) > 0)
                cfont++;
            else
                _Log("couldn't load font file %s", szFile);
        } while (FindNextFileA(hfind, &wfd));
        FindClose(hfind);
    }
    _Log("loaded %ld font files from %s", cfont, _stnFonts.Psz());
}

/***************************************************************************
    A text box asked for a font that isn't available; the system font is
    being used instead. Report each name once.
***************************************************************************/
void RAPP::_MissingFont(PSTN pstn)
{
    long istn;

    if (pvNil == vrapp._pgstMissingFonts && pvNil == (vrapp._pgstMissingFonts = GST::PgstNew(0)))
        return;
    if (vrapp._pgstMissingFonts->FFindStn(pstn, &istn))
        return;
    vrapp._pgstMissingFonts->FAddStn(pstn);
    vrapp._Log("missing font: %s (text will use the system font)", pstn->Psz());
    vrapp._Event("missing-font %s", pstn->Psz());
}
