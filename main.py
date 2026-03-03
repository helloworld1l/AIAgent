"""
主入口文件
"""
import sys
import argparse
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

app = FastAPI()


# 添加前端页面路由
@app.get("/")
async def get_frontend():
    return FileResponse("web_ui.html")

# 或者如果您想同时提供API和前端
@app.get("/ui")
async def get_ui():
    return FileResponse("web_ui.html")


sys.path.append(str(Path(__file__).parent))

def main():
    parser = argparse.ArgumentParser(description="MATLAB模型知识库与脚本生成助手")
    parser.add_argument(
        "mode",
        choices=["build", "run", "test", "api"],
        help="运行模式: build-构建知识库, run-交互生成模式, test-测试模式, api-启动API服务"
    )
    parser.add_argument(
        "--with-qdrant",
        action="store_true",
        help="仅在build模式下生效：启用Qdrant+SentenceTransformer向量索引构建"
    )
    
    args = parser.parse_args()
    
    if args.mode == "build":
        from knowledge_base.builder import main as build_main
        build_main(with_qdrant=args.with_qdrant)
    
    elif args.mode == "run":
        from agents.crm_agent import main as agent_main
        agent_main()
    
    elif args.mode == "test":
        from agents.crm_agent import CRMAgent
        agent = CRMAgent()
        agent.test_query()
    
    elif args.mode == "api":
        from api.server import run_server
        run_server()



if __name__ == "__main__":
    main()
