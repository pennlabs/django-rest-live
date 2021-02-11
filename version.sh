#!/bin/env bash
git commit -am "Release $1"
git push
git tag -a $1 -m "Release $1"
git push --tags
