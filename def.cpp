
// 消息定义模块:	System
// 消息定义注释:	定义系统仿真消息,用户可以作为触发消息
enum MSG_SIMU{
SM_START= 		10100,  // 仿真开始消息,仿真进程消息类起点 
SM_INFO   		,    	// 获得模型信息消息 
SM_INITIALIZE   ,    	// 仿真初始化消息 
SM_CONTINUE   	,    	// 仿真继续消息 
SM_STEPOVER   	,    		// 仿真一步结束消息 
SM_PAUSE   		,    	// 仿真暂停消息 
SM_STOP   		,    	// 仿真结束消息 
SM_DEBUGMODEL   ,    	// 仿真调试消息 
SM_BULIDMODEL   ,    	// 建立分析模型消息 
SM_STEPCHANGED  ,    	// 仿真步长改变消息 
SM_TIMEALIGN   	,    	// 时标对齐消息 
SM_WRITEDATA,			// 写数据文件消息 
SM_USERMSG   	,    	// 用户返回消息 
SM_BREAKPOINT   ,    	// 仿真到达断点 
SM_ERROR   		,    	// 仿真错误消息 
SM_CREATE   	,    	// 用户模块构造消息 
SM_DESTROY   	,    	// 用户模块销毁消息 
SM_DRAW   		,    	// 用户模块绘制消息 
SM_WRITE   		,    	// 用户模块数据存储消息 
SM_READ   		,    	// 用户模块数据读取消息 
SM_RESTART   	,    	// 重新启动一次仿真 
SM_END   		,    	// 一次仿真结束消息 
SM_MONTE   		,    	// 启动蒙特卡罗仿真 
SM_STOPMODEL   	,    	// 模块撤销消息 
SM_OUTPUT   	,    	// 模型输出消息 
SM_UPDATE   	,    	// 仿真完成一步或更新离散状态 
SM_RENEW	   	,    	// 更新状态消息 
SM_SIMUMETHOD   ,		// 仿真积分算法改变消息
SM_STOPALL		,		// 停止全部仿真
SM_SAVESNAP 	,    	// 通知用户保存当前状态
SM_LOADSNAP 	,   	// 通知用户加载当前状态
SM_NOACT   		,    	// 没有进行任何仿真动作 
SM_INITDATA,            // 初始化单元数据
};