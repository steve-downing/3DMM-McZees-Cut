/***************************************************************************
    3dmm-render: headless, deterministic .3mm movie renderer.

    Runs the real 3DMM playback engine (MVIE::Play and friends) against a
    frozen application clock that we advance by hand, so playback runs as
    fast as the machine allows and produces identical output every time.
    Every frame the engine would have put on screen is captured from the
    movie view into numbered BMPs, plus an ffconcat timeline with exact
    per-frame durations.

    Animated scene transitions (fades, dissolves) are not run through GDI;
    they are recorded and synthesized frame by frame from the before and
    after images, since the originals block on wall-clock time.
***************************************************************************/
#ifndef RENDER_H
#define RENDER_H

// A sound the movie used, extracted to <outdir>\sounds
struct SNDF
{
    PCRF pcrf;
    CTG ctg;
    CNO cno;
    ulong dtsLen; // length of one play, 0 if unknown
};

// One SiiPlay call: when it started and stopped on the movie timeline
struct CUE
{
    long sii;
    long isndf;
    CTG ctgDev;
    long sqn;
    long scl;
    long vlm;
    long cactPlay;
    ulong dtsOffset;
    ulong tsStart;
    ulong tsEnd;
};

// Master volume change (the engine fades the master volume at the end)
struct VLMEV
{
    ulong ts;
    long vlm;
};

/***************************************************************************
    Render sound device: plays nothing, keeps time. Every sound the
    engine plays is extracted once and logged as a cue on the movie
    timeline; "is it still playing?" is answered from the sound's real
    length, so wait-for-sound pauses behave as they do in 3DMM.
***************************************************************************/
typedef class RSDV *PRSDV;
#define RSDV_PAR SNDV
#define kclsRSDV 'RSDV'
class RSDV : public RSDV_PAR
{
    RTCLASS_DEC

  protected:
    CTG _ctg;

  public:
    RSDV(CTG ctg)
    {
        _ctg = ctg;
    }

    virtual bool FActive(void)
    {
        return fTrue;
    }
    virtual void Activate(bool fActive)
    {
    }
    virtual void Suspend(bool fSuspend)
    {
    }
    virtual void SetVlm(long vlm);
    virtual long VlmCur(void);

    virtual long SiiPlay(PRCA prca, CTG ctg, CNO cno, long sqn = ksqnNone, long vlm = kvlmFull, long cactPlay = 1,
                         ulong dtsStart = 0, long spr = 0, long scl = sclNil);

    virtual void Stop(long sii);
    virtual void StopAll(long sqn = sqnNil, long scl = sclNil);

    virtual void Pause(long sii)
    {
        Stop(sii);
    }
    virtual void PauseAll(long sqn = sqnNil, long scl = sclNil)
    {
        StopAll(sqn, scl);
    }
    virtual void Resume(long sii)
    {
    }
    virtual void ResumeAll(long sqn = sqnNil, long scl = sclNil)
    {
    }

    virtual bool FPlaying(long sii);
    virtual bool FPlayingAll(long sqn = sqnNil, long scl = sclNil);

    virtual void Flush(void)
    {
    }

    static long SiiNew(void)
    {
        return _SiiAlloc();
    }
};

typedef class RAPP *PRAPP;
#define RAPP_PAR APPB
#define kclsRAPP 'RAPP'
class RAPP : public RAPP_PAR
{
    RTCLASS_DEC

  protected:
    // command line
    STN _stnMovie;
    STN _stnOutDir;
    STN _stnRoot;
    ulong _dtsClickPause;
    ulong _dtsEndHold;
    long _cfrmLimit;
    bool _fStereo;
    double _pctDepth;
    double _pctPop;
    bool _fDebug;

    // engine objects
    PCFL _pcfl;
    PMVIE _pmvie;
    PGPT _pgptCapture;
    PGL _pglclrActive;

    // output state
    FILE *_pfileTimeline;
    FILE *_pfileEvents;
    FILE *_pfileLog;
    byte *_prgbEye;
    byte *_prgbPrev;
    byte *_prgbCur;
    byte *_prgbScratch;
    ushort *_prgsuDissolve;
    bool _fHavePrev;
    bool _fCapturing;
    long _cfrmOut;
    ulong _tsStart;
    ulong _dtsShift;
    ulong _dtsPendingStart;
    long _ifrmPending;
    bool _fInPause;
    ulong _tsPauseStart;
    long _lwExit;
    double _dzrConvergeLast;
    bool _fStereoValid;
    ulong _luTboxSig;
    BMAT34 _bmat34Stereo;
    double _dxrEye;
    double _dxpFocal;
    long _dxpShift;

    // audio
    PGL _pglsndf;
    PGL _pglcue;
    PGL _pglvlmev;
    long _vlmMaster;

    // init
    bool _FParseCommandLine(void);
    bool _FOpenOutput(void);
    bool _FInitContent(void);
    bool _FLoadMovie(void);

    // render
    bool _FRender(void);
    void _Pump(void);
    void _HandlePause(void);
    void _Capture(void);
    void _UpdatePalette(void);
    void _ConvertCapture(byte *prgbDst);
    void _PlaceEye(byte *prgbEye, byte *prgbFrame, long ieye, long dxpShift);
    void _DrawFrame(PMVU pmvu);
    void _DrawFlatStereo(PMVU pmvu);
    void _LogTextBoxes(void);
    void _DumpStereoDebug(PBWLD pbwld);
    long _DxpOut(void)
    {
        return _fStereo ? 2 * 544 : 544;
    }
    ulong _DtsOut(void);
    bool _FEmitFrame(byte *prgb, ulong dtsOut);
    void _EmitTransition(long trans, ulong dtsOut);
    void _FlushPendingFrame(ulong dtsOutNext);
    void _FinishTimeline(ulong dtsOutEnd);
    bool _FWriteBmp(PSTN pstnFile, byte *prgb);
    bool _FWriteSoundFile(SNDF *psndf, long isndf);
    void _WriteAudioScript(ulong dtsEnd);

    void _Log(PSZ pszFormat, ...);
    void _LogEngineErrors(PSZ pszContext);
    void _Event(PSZ pszFormat, ...);

    static bool _FInsertCD(PSTN pstnTitle);

    virtual bool _FInit(ulong grfapp, ulong grfgob, long ginDef);
    virtual bool _FInitOS(void);
    virtual bool _FInitMenu(void);
    virtual bool _FInitSound(long wav);
    virtual void _Loop(void);
    virtual void _CleanUp(void);

  public:
    RAPP(void);

    virtual void GetStnAppName(PSTN pstn);
    virtual void UpdateMarked(void);
    virtual tribool TGiveAlertSz(PSZ psz, long bk, long cok);

    // sound bookkeeping, called by RSDV
    long SiiPlaySound(CTG ctgDev, PRCA prca, CTG ctg, CNO cno, long sqn, long vlm, long cactPlay, ulong dtsStart,
                      long scl);
    void StopSounds(CTG ctgDev, long sii, long sqn, long scl);
    bool FSoundsPlaying(CTG ctgDev, long sii, long sqn, long scl);
    void SetMasterVlm(long vlm);
    long VlmMaster(void)
    {
        return _vlmMaster;
    }

    long LwExitCode(void)
    {
        return _lwExit;
    }
};

// Exit codes, so the batch script can tell failure modes apart.
enum
{
    klwExitOk = 0,
    klwExitUsage = 1,
    klwExitInit = 2,
    klwExitLoad = 3,
    klwExitMissingContent = 4,
    klwExitRender = 5,
    klwExitTimeout = 6,
};

#endif // RENDER_H
