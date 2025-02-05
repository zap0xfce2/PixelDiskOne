#/bin/bash

echo -e "\e[1;31mUpdating PixelDiskOne from source...\e[0m\n"

git clean -df
git reset --hard HEAD
git pull origin dev --force
