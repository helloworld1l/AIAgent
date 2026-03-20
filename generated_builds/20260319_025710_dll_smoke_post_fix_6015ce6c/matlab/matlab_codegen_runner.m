addpath('D:/python/rag_crm_agent/generated_builds/20260319_025710_dll_smoke_post_fix_6015ce6c/inputs');
cd('D:/python/rag_crm_agent/generated_builds/20260319_025710_dll_smoke_post_fix_6015ce6c/matlab');

cfg = coder.config('dll');
cfg.TargetLang = 'C';
cfg.GenerateReport = false;
cfg.GenCodeOnly = true;

codegen -config cfg dll_smoke -args {1.0};
exit;
