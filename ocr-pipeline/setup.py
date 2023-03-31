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
        "pandas==1.3.0",
        "numpy",
        "rawpy==0.17.0",
        "Pillow==7.0.0",
        "opencv-contrib-python==4.5.5.64",
        "jiwer==1.3.2",
        "jupyter==1.0.0",
        "matplotlib==3.1.0",
        "imageio==2.5.0",
        "parmap==1.5.2",
        "PyPDF2==1.26.0",
        "Wand==0.5.9",
        "PyMuPDF==1.19.6",
        "pyenchant==3.1.1",
        "nltk==3.5",
        "scikit-learn==0.23.1",
        "JPype1==0.7.5",
        "tesserocr==2.5.1"
    ],
    entry_points={
        'console_scripts': [
            'pipeline = ocr_pipeline.service.service:main'
        ]
    }
)
