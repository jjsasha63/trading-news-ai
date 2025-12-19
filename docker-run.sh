#!/bin/bash
docker build -t tna-trader .
docker run -d \
  --name tna-live \
  -v $(pwd)//app/data \
  -v $(pwd)/models:/app/models \
  -p 8001:8000 \
  tna-trader
