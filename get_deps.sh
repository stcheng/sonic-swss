#!/bin/bash
#
# This script is to build the dependencies of SONiC-SWSS
#
# USAGE:
#   ./get_deps.sh

mkdir deps
pushd deps

# Install REDIS HIREDIS
sudo apt-get install -y libjemalloc-dev
wget https://sonic-jenkins.westus.cloudapp.azure.com/job/redis-build/lastSuccessfulBuild/artifact/target/redis-tools_3.0.7-2_amd64.deb
wget https://sonic-jenkins.westus.cloudapp.azure.com/job/redis-build/lastSuccessfulBuild/artifact/target/redis-server_3.0.7-2_amd64.deb
wget https://sonic-jenkins.westus.cloudapp.azure.com/job/redis-build/lastSuccessfulBuild/artifact/target/redis-sentinel_3.0.7-2_amd64.deb

wget https://sonic-jenkins.westus.cloudapp.azure.com/job/hiredis-build/lastSuccessfulBuild/artifact/target/libhiredis0.13_0.13.3-2_amd64.deb
wget https://sonic-jenkins.westus.cloudapp.azure.com/job/hiredis-build/lastSuccessfulBuild/artifact/target/libhiredis-dev_0.13.3-2_amd64.deb
wget https://sonic-jenkins.westus.cloudapp.azure.com/job/hiredis-build/lastSuccessfulBuild/artifact/target/libhiredis-dbg_0.13.3-2_amd64.deb

sudo dpkg -i *.deb
popd

# TODO: Install SAI Implementation

# Get Quagga fpm.h
mkdir fpmsyncd/fpm
wget http://git.savannah.gnu.org/cgit/quagga.git/plain/fpm/fpm.h -O fpmsyncd/fpm/fpm.h
