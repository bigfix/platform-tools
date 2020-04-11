#!/bin/bash

TOKEN=$s8PnX13jItikQYLnaX1FesvdE

mkdir -p /opt/cylance/
cd /opt/cylance/
touch config_defaults.txt
echo InstallToken=$TOKEN > config_defaults.txt

cp (local CylancePROTECT.el7.rpm CylancePROTECTUI.el7.rpm) move to server /tmp

yum clean all

yum makecache fast

yum -y install CylancePROTECT.el7.rpm CylancePROTECTUI.el7.rpm



