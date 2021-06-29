from setuptools import find_packages, setup


setup(
    name="ocr_pipeline",
    version=0.1,
    description="reproducable ocr pipeline via rabbitmq",
    packages=find_packages(),
    install_requires=[
        "everett[yaml]",
        "kombu",
        "s3fs<0.3.0",
        "loguru",
        "pytesseract==0.3.1",
        "symspellpy==6.5.2",
        "pandas==0.24.2",
        "numpy==1.16.5",
        "rawpy==0.13.1",
        "Pillow==7.0.0",
        "opencv-python==4.1.2.30",
        "jiwer==1.3.2",
        "jupyter==1.0.0",
        "matplotlib==3.1.0",
        "imageio==2.5.0",
        "parmap==1.5.2",
        "PyPDF2==1.26.0",
        "Wand==0.5.9",
        "PyMuPDF==1.17.4",
        "torch==1.5.0",
        "pytorch-pretrained-bert==0.6.2",
        "pyenchant==3.1.1",
        "nltk==3.5",
        "scikit-learn==0.23.1",
        "JPype1==0.7.5",
        "sutime==1.0.0rc5",
        "tesserocr==2.5.1"
    ],
    entry_points={
        'console_scripts': [
            'pipeline = ocr_pipeline.service.service:main'
        ]
    }
)
