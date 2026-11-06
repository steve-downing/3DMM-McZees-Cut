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
    long _cfrmLimit;

    // engine objects
    PCFL _pcfl;
    PMVIE _pmvie;
    PGPT _pgptCapture;
    PGL _pglclrActive;

    // output state
    FILE *_pfileTimeline;
    FILE *_pfileEvents;
    FILE *_pfileLog;
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
    ulong _DtsOut(void);
    bool _FEmitFrame(byte *prgb, ulong dtsOut);
    void _EmitTransition(long trans, ulong dtsOut);
    void _FlushPendingFrame(ulong dtsOutNext);
    void _FinishTimeline(ulong dtsOutEnd);
    bool _FWriteBmp(PSTN pstnFile, byte *prgb);

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
