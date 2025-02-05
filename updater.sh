#/bin/bash

echo "Updating PixelDiskOne from source..."

git clean -df
git reset --hard HEAD
git pull origin dev --force
