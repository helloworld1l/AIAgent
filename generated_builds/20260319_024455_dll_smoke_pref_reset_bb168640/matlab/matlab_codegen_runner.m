addpath('D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/inputs');
cd('D:/python/rag_crm_agent/generated_builds/20260319_024455_dll_smoke_pref_reset_bb168640/matlab');

cfg = coder.config('dll');
cfg.TargetLang = 'C';
cfg.GenerateReport = false;

codegen -config cfg dll_smoke -args {1.0};
exit;
