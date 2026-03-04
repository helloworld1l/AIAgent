"""
主入口文件
"""
import sys
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

def main():
    parser = argparse.ArgumentParser(description="对话式AI助手（支持MATLAB建模与.m文件生成）")
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
