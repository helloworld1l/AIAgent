addpath('D:/python/rag_crm_agent/generated_builds/20260319_023003_dll_smoke_prefdir_workaround_40f6bf59/inputs');
cd('D:/python/rag_crm_agent/generated_builds/20260319_023003_dll_smoke_prefdir_workaround_40f6bf59/matlab');

cfg = coder.config('dll');
cfg.TargetLang = 'C';
cfg.GenerateReport = false;

codegen -config cfg dll_smoke -args {1.0};
exit;
