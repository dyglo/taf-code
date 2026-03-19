from setuptools import setup, find_packages

setup(
    name="gemini-code",
    version="1.0.0",
    description="AI-powered coding assistant for your terminal, powered by Gemini",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "google-genai>=1.0.0",
        "rich>=13.0.0",
        "prompt_toolkit>=3.0.0",
        "pygments>=2.0.0",
        "pathspec>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "gemini-code=taf_code.main:main",
            "gc=taf_code.main:main",
        ],
    },
)
