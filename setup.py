from setuptools import setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="django_microsys",
    version="1.8.1",
    author="DeBeski",
    author_email="debeski1@gmail.com",
    description="Django micro (System Integration Service) - Multilingual Django Starter Pack, Packed with Features.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/debeski/django-microsys",
    packages=["microsys"],
    include_package_data=True,
    classifiers=[
        "Framework :: Django",
        "Framework :: Django :: 5",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    install_requires=[
        "Django>=5.1",
        "django-crispy-forms>=2.4",
        "django-tables2>=2.7",
        "django-filter>=24.3",
        "pillow>=11.0",
        "babel>=2.1",
    ],
    license="MIT",
)
