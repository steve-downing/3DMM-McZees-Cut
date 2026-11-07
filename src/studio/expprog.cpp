/* McZee's Cut: a panel showing the progress of exports (see inc/expprog.h). */
#include <string.h>
#include "studio.h"
#include "expprog.h"
ASSERTNAME

const long kcjobMax = 4;    // exports shown at once
const long kdxpPanel = 300; // panel width
const long kdypRow = 30;    // one export: a line of text and a bar
const long kdypPad = 6;
const long kypPanel = 6; // from the top of the screen

enum
{
    kstateRun,
    kstateDone,
    kstateFail,
};

struct EXPJ
{
    long pid;
    long state;
    long pct;
    achar sz[128];
};

static EXPJ _rgjob[kcjobMax];
static long _cjob = 0;
static long _hidPanel = hidNil;

/***************************************************************************
    The panel: a dark box with a line of text and a bar per export. Mouse
    clicks go through it to whatever is underneath.
***************************************************************************/
#define EXPP_PAR GOB
#define kclsEXPP 'EXPP'
class EXPP : public EXPP_PAR
{
    RTCLASS_DEC

  public:
    EXPP(PGCB pgcb) : EXPP_PAR(pgcb)
    {
    }
    virtual void Draw(PGNV pgnv, RC *prcClip);
    virtual bool FPtIn(long xp, long yp)
    {
        return fFalse;
    }
};
RTCLASS(EXPP)

void EXPP::Draw(PGNV pgnv, RC *prcClip)
{
    RC rc, rcT;
    long ijob, yp, dxp;
    achar sz[160];
    STN stn;
    ACR acrPanel(0x26, 0x1C, 0x4A);
    ACR acrTrack(0x50, 0x46, 0x78);
    ACR acrBar(0xFF, 0xD2, 0x28);
    ACR acrDone(0x5A, 0xD2, 0x5A);
    ACR acrFail(0xFF, 0x78, 0x78);

    GetRc(&rc, cooLocal);
    pgnv->FillRc(&rc, acrPanel);
    pgnv->FrameRc(&rc, acrBar);
    pgnv->SetFont(vapp.OnnDefVariable(), fontNil, 12, tahLeft, tavTop);
    for (ijob = 0; ijob < _cjob; ijob++)
    {
        EXPJ *pjob = &_rgjob[ijob];

        yp = rc.ypTop + kdypPad + ijob * kdypRow;
        if (pjob->state == kstateRun)
            wsprintf(sz, PszLit("%s  %ld%%"), pjob->sz, pjob->pct);
        else
            wsprintf(sz, PszLit("%s"), pjob->sz);
        stn.SetSz(sz);
        pgnv->DrawStn(&stn, rc.xpLeft + 8, yp, pjob->state == kstateFail ? acrFail : kacrWhite, kacrClear);

        rcT.Set(rc.xpLeft + 8, yp + 18, rc.xpRight - 8, yp + 24);
        pgnv->FillRc(&rcT, acrTrack);
        dxp = (rcT.xpRight - rcT.xpLeft) * LwMin(100, LwMax(0, pjob->pct)) / 100;
        if (pjob->state == kstateFail)
            dxp = rcT.xpRight - rcT.xpLeft;
        rcT.xpRight = rcT.xpLeft + dxp;
        if (dxp > 0)
            pgnv->FillRc(&rcT, pjob->state == kstateDone ? acrDone : pjob->state == kstateFail ? acrFail : acrBar);
    }
}

/***************************************************************************
    Movie Exporter's reports. lw points at a COPYDATASTRUCT that's only good
    during this call, so copy what we need and let the command loop do the
    drawing.
***************************************************************************/
bool FExportProgressMessage(uint wm, LPARAM lw, long *plwRet)
{
    COPYDATASTRUCT *pcds = (COPYDATASTRUCT *)lw;
    achar sz[256];
    achar *pch;
    long pid = 0, pct = 0, state, ijob, cb;

    if (wm != WM_COPYDATA || pvNil == pcds || pcds->dwData != kdwExportProgress || pvNil == pcds->lpData ||
        pcds->cbData < 1)
    {
        return fFalse;
    }
    cb = LwMin((long)pcds->cbData, size(sz) - 1);
    CopyPb(pcds->lpData, sz, cb);
    sz[cb] = 0;

    // "<pid> <state> <percent> <text>"
    for (pch = sz; *pch >= ChLit('0') && *pch <= ChLit('9'); pch++)
        pid = pid * 10 + (*pch - ChLit('0'));
    if (*pch++ != ChLit(' '))
        return fFalse;
    if (0 == strncmp(pch, "run ", 4))
        state = kstateRun;
    else if (0 == strncmp(pch, "done ", 5))
        state = kstateDone;
    else if (0 == strncmp(pch, "fail ", 5))
        state = kstateFail;
    else if (0 == strncmp(pch, "hide ", 5))
        state = -1;
    else
        return fFalse;
    while (*pch && *pch != ChLit(' '))
        pch++;
    if (*pch == ChLit(' '))
        pch++;
    for (; *pch >= ChLit('0') && *pch <= ChLit('9'); pch++)
        pct = pct * 10 + (*pch - ChLit('0'));
    if (*pch == ChLit(' '))
        pch++;

    for (ijob = 0; ijob < _cjob && _rgjob[ijob].pid != pid; ijob++)
        ;
    if (state < 0)
    {
        // done with this one
        if (ijob < _cjob)
        {
            for (; ijob + 1 < _cjob; ijob++)
                _rgjob[ijob] = _rgjob[ijob + 1];
            _cjob--;
        }
    }
    else
    {
        if (ijob == _cjob)
        {
            if (_cjob == kcjobMax)
            {
                // drop the oldest
                for (ijob = 0; ijob + 1 < _cjob; ijob++)
                    _rgjob[ijob] = _rgjob[ijob + 1];
                _cjob--;
            }
            ijob = _cjob++;
            _rgjob[ijob].pid = pid;
        }
        _rgjob[ijob].state = state;
        _rgjob[ijob].pct = pct;
        lstrcpyn(_rgjob[ijob].sz, pch, CvFromRgv(_rgjob[ijob].sz));
    }

    if (pvNil != vpcex)
        vpcex->EnqueueCid(cidExportProgress, &vapp);
    *plwRet = fTrue;
    return fTrue;
}

void UpdateExportProgress(void)
{
    PGOB pgobPar = vapp.Pkwa();
    PGOB pgob;
    RC rcAbs, rcRel;
    GCB gcb;

    if (pvNil == pgobPar)
        return;
    pgob = (hidNil == _hidPanel) ? pvNil : pgobPar->PgobFromHid(_hidPanel);
    if (_cjob == 0)
    {
        if (pvNil != pgob)
            ReleasePpo(&pgob);
        _hidPanel = hidNil;
        return;
    }

    // centered across the top
    rcRel.Set(krelOne / 2, krelZero, krelOne / 2, krelZero);
    rcAbs.Set(-kdxpPanel / 2, kypPanel, kdxpPanel / 2, kypPanel + 2 * kdypPad + _cjob * kdypRow - 6);
    if (pvNil == pgob)
    {
        _hidPanel = GOB::HidUnique();
        gcb.Set(_hidPanel, pgobPar, fgobNil, kginMark, &rcAbs, &rcRel);
        if (pvNil == (pgob = NewObj EXPP(&gcb)))
        {
            _hidPanel = hidNil;
            return;
        }
    }
    else
    {
        pgob->SetPos(&rcAbs, &rcRel);
        pgob->SendBehind(pvNil); // in front of whatever room has opened since
    }
    pgob->InvalRc(pvNil, kginMark);
}
