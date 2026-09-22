source myenv/bin/activate
 python3 extract_slides_V2.py 05.mp4 --check-only
python3 extract_slides_V2.py  05.mp4 slides_pod --pixel-diff 50 --min-gap 0.1 --capture-delay 0.3 --changed-ratio 0.003240 --sample-interval 0.10

