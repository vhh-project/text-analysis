#!/bin/bash
# new: fetch only desired files

echo "-- fetch_tess_traindata --"
mkdir /home/work/tessdata_fast/
mkdir /home/work/tessdata_best/

tess_traindata=("deu.traineddata" "eng.traineddata" "fra.traineddata" "pol.traineddata" "rus.traineddata" "ukr.traineddata" "fin.traineddata")
for i in "${tess_traindata[@]}"
do
    wget -nv "https://github.com/tesseract-ocr/tessdata_fast/blob/main/"$i"?raw=true" -O /home/work/tessdata_fast/$i
    wget -nv "https://github.com/tesseract-ocr/tessdata_best/blob/main/"$i"?raw=true" -O /home/work/tessdata_best/$i
done

tess_traindata_script=( "Cyrillic.traineddata" "Fraktur.traineddata" )
for i in "${tess_traindata_script[@]}"
do
    wget -nv "https://github.com/tesseract-ocr/tessdata_fast/tree/main/script/"$i"?raw=true" -O /home/work/tessdata_fast/script/$i
    wget -nv "https://github.com/tesseract-ocr/tessdata_best/tree/main/script/"$i"?raw=true" -O /home/work/tessdata_best/script/$i
done

cd /home/work/tessdata_best/

git clone https://github.com/tesseract-ocr/tessconfigs.git
cp -R /home/work/tessdata_best/tessconfigs/configs/ /home/work/tessdata_best/
wget -nv https://github.com/tesseract-ocr/tessdata_best/blob/master/pdf.ttf
