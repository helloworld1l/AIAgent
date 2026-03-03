import sys
print(f"Python 版本: {sys.version}")
print(f"Python 路径: {sys.executable}")

try:
    import torch
    print(f"✓ PyTorch 版本: {torch.__version__}")
except ImportError:
    print("✗ PyTorch 未安装")

try:
    import langchain
    print(f"✓ LangChain 版本: {langchain.__version__}")
except ImportError:
    print("✗ LangChain 未安装")

# ... 可继续添加其他包的验证
print("\n环境验证完成。")