source myenv/bin/activate
 python3 extract_slides_V2.py 05.mp4 --check-only
python3 extract_slides_V2.py  05.mp4 slides_pod --pixel-diff 80 --min-gap 2.0 --capture-delay 0.3 --changed-ratio 0.03240 --sample-interval 0.10

