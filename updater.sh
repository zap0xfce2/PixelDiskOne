#/bin/bash

echo "Updating PixelDiskOne from Source..."

git clean -df
git reset --hard HEAD
git pull origin main --force
