/***************************************************************************
    3dmm-render: headless, deterministic .3mm movie renderer.  See render.h.

    Usage:
        3dmm-render <movie.3mm> <outdir> [--root <dir>] [--click-pause <sec>]
                    [--max-frames <n>]

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
#include "render.h"
#include "basepal.h"

ASSERTNAME

RTCLASS(RAPP)

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
                        "[--max-frames <n>]\n");
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
    _Log("movie: %s", _stnMovie.Psz());
    _Log("content root: %s", _stnRoot.Psz());
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
    A sound manager with no output devices: the engine can queue sounds
    freely and nothing comes out of the speakers mid-render.
***************************************************************************/
bool RAPP::_FInitSound(long wav)
{
    if (pvNil == vpsndm)
        vpsndm = SNDM::PsndmNew();
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
    long cpx = kdxpRender * kdypRender;
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

    _prgbPrev = (byte *)malloc(cpx * 3);
    _prgbCur = (byte *)malloc(cpx * 3);
    _prgbScratch = (byte *)malloc(cpx * 3);
    _prgsuDissolve = (ushort *)malloc(cpx * size(ushort));
    if (pvNil == _prgbPrev || pvNil == _prgbCur || pvNil == _prgbScratch || pvNil == _prgsuDissolve)
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
    return TsCurrent() - _tsStart + _dtsShift;
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

void RAPP::_Capture(void)
{
    PMVU pmvu;
    TRANS trans;
    ulong dtsOut;
    byte *prgbT;
    long cb = kdxpRender * kdypRender * 3;

    if (pvNil == _pmvie || pvNil == _pgptCapture || pvNil == (pmvu = _pmvie->PmvuCur()))
        return;

    // Animated transitions are synthesized below rather than run, so
    // clear the request before anything tries to animate it.
    trans = _pmvie->Trans();
    if (trans != transNil)
        _pmvie->SetTrans(transNil);

    _UpdatePalette();
    pmvu->DrawTree(_pgptCapture, pvNil, pvNil, fgobNil);
    _ConvertCapture(_prgbCur);
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
    long cpx = kdxpRender * kdypRender;
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
    _dtsShift += kdtsTransition;
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
    long cbRow = kdxpRender * 3; // already a multiple of 4
    long cbImage = cbRow * kdypRender;
    long cbFile = size(rgbHeader) + cbImage;
    long yp, xp;
    byte rgbRow[kdxpRender * 3];

    ClearPb(rgbHeader, size(rgbHeader));
    rgbHeader[0] = 'B';
    rgbHeader[1] = 'M';
    *(long *)(rgbHeader + 2) = cbFile;
    *(long *)(rgbHeader + 10) = size(rgbHeader);
    *(long *)(rgbHeader + 14) = 40;
    *(long *)(rgbHeader + 18) = kdxpRender;
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
        for (xp = 0; xp < kdxpRender; xp++)
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
    ReleasePpo(&_pmvie);
    ReleasePpo(&_pgptCapture);
    ReleasePpo(&_pglclrActive);
    ReleasePpo(&_pcfl);
    ReleasePpo(&vptagm);
    free(_prgbPrev);
    free(_prgbCur);
    free(_prgbScratch);
    free(_prgsuDissolve);
    _prgbPrev = _prgbCur = _prgbScratch = pvNil;
    _prgsuDissolve = pvNil;
    if (pvNil != _pfileEvents)
        fclose(_pfileEvents);
    _pfileEvents = pvNil;
    _Log("exit code %ld", _lwExit);
    if (pvNil != _pfileLog)
        fclose(_pfileLog);
    _pfileLog = pvNil;
    RAPP_PAR::_CleanUp();
}
