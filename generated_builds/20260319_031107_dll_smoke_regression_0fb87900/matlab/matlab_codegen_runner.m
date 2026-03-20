addpath('D:/python/rag_crm_agent/generated_builds/20260319_031107_dll_smoke_regression_0fb87900/inputs');
cd('D:/python/rag_crm_agent/generated_builds/20260319_031107_dll_smoke_regression_0fb87900/matlab');

cfg = coder.config('dll');
cfg.TargetLang = 'C';
cfg.GenerateReport = false;
cfg.GenCodeOnly = true;

codegen -config cfg dll_smoke -args {1.0};
exit;
