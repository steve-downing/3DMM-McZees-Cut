/* McZee's Cut: progress of the exports Movie Exporter runs for us.

   File > Export starts Movie Exporter in the background with our window's
   handle. It does its work without a window of its own and reports with
   WM_COPYDATA (tagged kdwExportProgress): "<pid> <run|done|fail|hide>
   <percent> <text>". We keep a small panel over the top of the screen with
   a bar for each export, wherever the user goes in the building. */
#ifndef EXPPROG_H
#define EXPPROG_H

const ulong kdwExportProgress = 0x58455A4D; // 'MZEX'

// From the frame window procedure: handles Movie Exporter's WM_COPYDATA
bool FExportProgressMessage(uint wm, LPARAM lw, long *plwRet);

// On cidExportProgress: show, update or take down the panel
void UpdateExportProgress(void);

#endif // !EXPPROG_H
