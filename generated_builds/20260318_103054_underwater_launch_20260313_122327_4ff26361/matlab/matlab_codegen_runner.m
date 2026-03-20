addpath('D:/python/rag_crm_agent/generated_builds/20260318_103054_underwater_launch_20260313_122327_4ff26361/inputs');
cd('D:/python/rag_crm_agent/generated_builds/20260318_103054_underwater_launch_20260313_122327_4ff26361/matlab');

cfg = coder.config('lib');
cfg.TargetLang = 'C++';
cfg.GenerateReport = true;

codegen -config cfg underwater_launch_main -args {};
exit;
