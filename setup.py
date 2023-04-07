from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="fy_rest",
    version="0.1.0",
    author="Florian 'Fy' Gasquez",
    author_email="m@fy.to",
    description="A Flask extension for creating RESTful APIs with TypeScript type generation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Fy-/FyRest",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Framework :: Flask",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    python_requires=">=3.7",
    install_requires=[
        "Flask>=1.0",
        "click>=8.0"
    ],
)