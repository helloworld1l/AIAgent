/*
 * File: _coder_rocket_launch_1d_mex.h
 *
 * MATLAB Coder version            : 24.1
 * C/C++ source code generated on  : 2026-03-20 11:24:39
 */

#ifndef _CODER_ROCKET_LAUNCH_1D_MEX_H
#define _CODER_ROCKET_LAUNCH_1D_MEX_H

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

void unsafe_rocket_launch_1d_mexFunction(int32_T nlhs, mxArray *plhs[2],
                                         int32_T nrhs, const mxArray *prhs[5]);

#ifdef __cplusplus
}
#endif

#endif
/*
 * File trailer for _coder_rocket_launch_1d_mex.h
 *
 * [EOF]
 */
