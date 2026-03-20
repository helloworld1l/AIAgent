addpath('D:/python/rag_crm_agent/generated_builds/20260318_103208_underwater_launch_20260313_122327_7ccdd9ab/inputs');
cd('D:/python/rag_crm_agent/generated_builds/20260318_103208_underwater_launch_20260313_122327_7ccdd9ab/matlab');

cfg = coder.config('lib');
cfg.TargetLang = 'C++';
cfg.GenerateReport = true;

codegen -config cfg underwater_launch_main -args {};
exit;
