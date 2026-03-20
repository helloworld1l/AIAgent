/*
 * File: main.c
 *
 * MATLAB Coder version            : 24.1
 * C/C++ source code generated on  : 2026-03-20 12:25:12
 */

/*************************************************************************/
/* This automatically generated example C main file shows how to call    */
/* entry-point functions that MATLAB Coder generated. You must customize */
/* this file for your application. Do not modify this file directly.     */
/* Instead, make a copy of this file, modify it, and integrate it into   */
/* your development environment.                                         */
/*                                                                       */
/* This file initializes entry-point function arguments to a default     */
/* size and value before calling the entry-point functions. It does      */
/* not store or use any values returned from the entry-point functions.  */
/* If necessary, it does pre-allocate memory for returned values.        */
/* You can use this file as a starting point for a main function that    */
/* you can deploy in your application.                                   */
/*                                                                       */
/* After you copy the file, and before you deploy it, you must make the  */
/* following changes:                                                    */
/* * For variable-size function arguments, change the example sizes to   */
/* the sizes that your application requires.                             */
/* * Change the example values of function arguments to the values that  */
/* your application requires.                                            */
/* * If the entry-point functions return values, store these values or   */
/* otherwise use them as required by your application.                   */
/*                                                                       */
/*************************************************************************/

/* Include Files */
#include "main.h"
#include "rocket_launch_1d.h"
#include "rocket_launch_1d_terminate.h"
#include "rt_nonfinite.h"

/* Function Declarations */
static void argInit_2x1_real_T(double result[2]);

static void argInit_3x1_real_T(double result[3]);

static double argInit_real_T(void);

/* Function Definitions */
/*
 * Arguments    : double result[2]
 * Return Type  : void
 */
static void argInit_2x1_real_T(double result[2])
{
  int idx0;
  /* Loop over the array to initialize each element. */
  for (idx0 = 0; idx0 < 2; idx0++) {
    /* Set the value of the array element.
Change this value to the value that the application requires. */
    result[idx0] = argInit_real_T();
  }
}

/*
 * Arguments    : double result[3]
 * Return Type  : void
 */
static void argInit_3x1_real_T(double result[3])
{
  int idx0;
  /* Loop over the array to initialize each element. */
  for (idx0 = 0; idx0 < 3; idx0++) {
    /* Set the value of the array element.
Change this value to the value that the application requires. */
    result[idx0] = argInit_real_T();
  }
}

/*
 * Arguments    : void
 * Return Type  : double
 */
static double argInit_real_T(void)
{
  return 0.0;
}

/*
 * Arguments    : int argc
 *                char **argv
 * Return Type  : int
 */
int main(int argc, char **argv)
{
  (void)argc;
  (void)argv;
  /* The initialize function is being called automatically from your entry-point
   * function. So, a call to initialize is not included here. */
  /* Invoke the entry-point functions.
You can call entry-point functions multiple times. */
  main_rocket_launch_1d();
  /* Terminate the application.
You do not need to do this more than one time. */
  rocket_launch_1d_terminate();
  return 0;
}

/*
 * Arguments    : void
 * Return Type  : void
 */
void main_rocket_launch_1d(void)
{
  double dv[3];
  double f[3];
  double dv1[2];
  double y[2];
  double mode_tmp;
  /* Initialize function 'rocket_launch_1d' input arguments. */
  mode_tmp = argInit_real_T();
  /* Initialize function input argument 'x'. */
  /* Initialize function input argument 'u'. */
  /* Call the entry-point 'rocket_launch_1d'. */
  argInit_3x1_real_T(dv);
  argInit_2x1_real_T(dv1);
  rocket_launch_1d(mode_tmp, mode_tmp, mode_tmp, dv, dv1, y, f);
}

/*
 * File trailer for main.c
 *
 * [EOF]
 */
