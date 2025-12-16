from setuptools import setup, find_packages

setup(
    name="trading-news-ai",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "pandas>=2.0.0",
        "yfinance>=0.2.0",
        "beautifulsoup4>=4.12.0",
        "lxml>=5.0.0",
        "PyYAML>=6.0",
        "requests>=2.31.0",
        "scikit-learn>=1.3.0",
    ],
)
