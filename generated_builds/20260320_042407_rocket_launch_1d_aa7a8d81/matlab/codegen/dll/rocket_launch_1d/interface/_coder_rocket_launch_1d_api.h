/*
 * File: _coder_rocket_launch_1d_api.h
 *
 * MATLAB Coder version            : 24.1
 * C/C++ source code generated on  : 2026-03-20 12:25:12
 */

#ifndef _CODER_ROCKET_LAUNCH_1D_API_H
#define _CODER_ROCKET_LAUNCH_1D_API_H

/* Include Files */
#include "emlrt.h"
#include "mex.h"
#include "tmwtypes.h"
#include <string.h>

/* Variable Declarations */
extern emlrtCTX emlrtRootTLSGlobal;
extern emlrtContext emlrtContextGlobal;

#ifdef __cplusplus
extern "C" {
#endif

/* Function Declarations */
void rocket_launch_1d(real_T mode, real_T b_time, real_T Ts, real_T x[3],
                      real_T u[2], real_T y[2], real_T f[3]);

void rocket_launch_1d_api(const mxArray *const prhs[5], int32_T nlhs,
                          const mxArray *plhs[2]);

void rocket_launch_1d_atexit(void);

void rocket_launch_1d_initialize(void);

void rocket_launch_1d_terminate(void);

void rocket_launch_1d_xil_shutdown(void);

void rocket_launch_1d_xil_terminate(void);

#ifdef __cplusplus
}
#endif

#endif
/*
 * File trailer for _coder_rocket_launch_1d_api.h
 *
 * [EOF]
 */
