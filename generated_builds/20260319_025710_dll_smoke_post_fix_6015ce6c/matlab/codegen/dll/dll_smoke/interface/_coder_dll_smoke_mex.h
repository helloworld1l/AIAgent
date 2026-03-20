/*
 * File: _coder_dll_smoke_mex.h
 *
 * MATLAB Coder version            : 24.1
 * C/C++ source code generated on  : 2026-03-19 10:58:17
 */

#ifndef _CODER_DLL_SMOKE_MEX_H
#define _CODER_DLL_SMOKE_MEX_H

/* Include Files */
#include "emlrt.h"
#include "mex.h"
#include "tmwtypes.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Function Declarations */
MEXFUNCTION_LINKAGE void mexFunction(int32_T nlhs, mxArray *plhs[],
                                     int32_T nrhs, const mxArray *prhs[]);

emlrtCTX mexFunctionCreateRootTLS(void);

void unsafe_dll_smoke_mexFunction(int32_T nlhs, mxArray *plhs[1], int32_T nrhs,
                                  const mxArray *prhs[1]);

#ifdef __cplusplus
}
#endif

#endif
/*
 * File trailer for _coder_dll_smoke_mex.h
 *
 * [EOF]
 */
