/*
 * File: _coder_dll_smoke_api.h
 *
 * MATLAB Coder version            : 24.1
 * C/C++ source code generated on  : 2026-03-19 10:46:06
 */

#ifndef _CODER_DLL_SMOKE_API_H
#define _CODER_DLL_SMOKE_API_H

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
real_T dll_smoke(real_T x);

void dll_smoke_api(const mxArray *prhs, const mxArray **plhs);

void dll_smoke_atexit(void);

void dll_smoke_initialize(void);

void dll_smoke_terminate(void);

void dll_smoke_xil_shutdown(void);

void dll_smoke_xil_terminate(void);

#ifdef __cplusplus
}
#endif

#endif
/*
 * File trailer for _coder_dll_smoke_api.h
 *
 * [EOF]
 */
