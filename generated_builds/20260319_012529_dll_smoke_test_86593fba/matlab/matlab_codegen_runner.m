addpath('D:/python/rag_crm_agent/generated_builds/20260319_012529_dll_smoke_test_86593fba/inputs');
cd('D:/python/rag_crm_agent/generated_builds/20260319_012529_dll_smoke_test_86593fba/matlab');

cfg = coder.config('dll');
cfg.TargetLang = 'C';
cfg.GenerateReport = false;

codegen -config cfg dll_smoke -args {1.0};
exit;
