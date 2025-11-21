from setuptools import setup, find_packages

setup(
    py_modules=[
        "email_parser",
        "html_processor",
        "json_processor",
        "header_adapters",
    ],
    packages=find_packages(include=["tests", "tests.*"]),
)
