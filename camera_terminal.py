#!/usr/bin/env python3
"""
=============================================================
  NWS RADAR — TRAFFIC CAMERA FEED TERMINAL  v2
  Python backend for traffic camera stream health monitoring
=============================================================
  Each camera has a `streams` list (ordered by preference).
  On failure the monitor tries each fallback in order, logging:
    "OFFLINE  ny-ta-111 — I-90 Thruway @ Amsterdam has gone
     offline, switching to stream 2..."

  The terminal NEVER resets — lines are appended forever.
  Log tail is written to camera_status.json so index.html
  can poll it.

  Usage:
      python camera_terminal.py                  # continuous loop
      python camera_terminal.py --once           # single scan, exit
      python camera_terminal.py --interval 60    # custom interval (sec)
      python camera_terminal.py --state NY       # filter by state
      python camera_terminal.py --open           # open browser on start
      python camera_terminal.py --log FILE.log   # custom log path
=============================================================
"""

import argparse, datetime, json, os, sys, time
import urllib.request, urllib.error, webbrowser
from pathlib import Path

RESET="\033[0m"; CYAN="\033[96m"; GREEN="\033[92m"; YELLOW="\033[93m"
RED="\033[91m";  DIM="\033[2m";   BOLD="\033[1m";   WHITE="\033[97m"
MAX_LOG_LINES = 2000

TRAFFIC_CAMERAS = [
  # NEW YORK
  {"id":"ny-r1-036",  "name":"I-87 Northway @ Exit 15",        "city":"Saratoga Springs","state":"NY","lat":43.083,"lng":-73.774,"provider":"NYSDOT","streams":["https://s51.nysdot.skyvdn.com:443/rtplive/R1_036/playlist.m3u8","https://s53.nysdot.skyvdn.com:443/rtplive/R1_036/playlist.m3u8","https://s9.nysdot.skyvdn.com:443/rtplive/R1_036/playlist.m3u8"]},
  {"id":"ny-r1-023",  "name":"I-87 Northway @ Exit 13N",       "city":"Saratoga Springs","state":"NY","lat":43.003,"lng":-73.785,"provider":"NYSDOT","streams":["https://s53.nysdot.skyvdn.com:443/rtplive/R1_023/playlist.m3u8","https://s51.nysdot.skyvdn.com:443/rtplive/R1_023/playlist.m3u8"]},
  {"id":"ny-r1-2107", "name":"I-87 Northway @ Exit 14",        "city":"Saratoga Springs","state":"NY","lat":43.055,"lng":-73.804,"provider":"NYSDOT","streams":["https://s9.nysdot.skyvdn.com:443/rtplive/R1_2107/playlist.m3u8","https://s51.nysdot.skyvdn.com:443/rtplive/R1_2107/playlist.m3u8"]},
  {"id":"ny-ta-100",  "name":"I-87 Thruway @ Tarrytown",       "city":"Tarrytown","state":"NY","lat":41.073,"lng":-73.918,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_100/playlist.m3u8","https://s51.nysdot.skyvdn.com:443/rtplive/TA_100/playlist.m3u8"]},
  {"id":"ny-ta-101",  "name":"I-87 Thruway @ Tarrytown South", "city":"Tarrytown","state":"NY","lat":41.065,"lng":-73.915,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_101/playlist.m3u8"]},
  {"id":"ny-ta-102",  "name":"I-87 Thruway @ Yonkers",         "city":"Yonkers","state":"NY","lat":40.958,"lng":-73.875,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_102/playlist.m3u8"]},
  {"id":"ny-ta-103",  "name":"I-87 Thruway @ Suffern",         "city":"Suffern","state":"NY","lat":41.116,"lng":-74.149,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_103/playlist.m3u8"]},
  {"id":"ny-ta-104",  "name":"I-87 Thruway @ Harriman",        "city":"Harriman","state":"NY","lat":41.306,"lng":-74.147,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_104/playlist.m3u8"]},
  {"id":"ny-ta-105",  "name":"I-87 Thruway @ Newburgh",        "city":"Newburgh","state":"NY","lat":41.500,"lng":-74.010,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_105/playlist.m3u8"]},
  {"id":"ny-ta-106",  "name":"I-87 Thruway @ Kingston",        "city":"Kingston","state":"NY","lat":41.930,"lng":-73.988,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_106/playlist.m3u8"]},
  {"id":"ny-ta-107",  "name":"I-87 Thruway @ Catskill",        "city":"Catskill","state":"NY","lat":42.211,"lng":-73.869,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_107/playlist.m3u8"]},
  {"id":"ny-ta-108",  "name":"I-87 Thruway @ Coxsackie",       "city":"Coxsackie","state":"NY","lat":42.365,"lng":-73.823,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_108/playlist.m3u8"]},
  {"id":"ny-ta-109",  "name":"I-87 Thruway @ Albany Interchange","city":"Albany","state":"NY","lat":42.691,"lng":-73.813,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_109/playlist.m3u8"]},
  {"id":"ny-ta-110",  "name":"I-90 Thruway @ Schenectady",     "city":"Schenectady","state":"NY","lat":42.793,"lng":-73.975,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_110/playlist.m3u8"]},
  {"id":"ny-ta-111",  "name":"I-90 Thruway @ Amsterdam",       "city":"Amsterdam","state":"NY","lat":42.936,"lng":-74.183,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_111/playlist.m3u8"]},
  {"id":"ny-ta-112",  "name":"I-90 Thruway @ Utica",           "city":"Utica","state":"NY","lat":43.094,"lng":-75.233,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_112/playlist.m3u8"]},
  {"id":"ny-ta-113",  "name":"I-90 Thruway @ Syracuse",        "city":"Syracuse","state":"NY","lat":43.048,"lng":-76.147,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_113/playlist.m3u8"]},
  {"id":"ny-ta-114",  "name":"I-90 Thruway @ Rochester",       "city":"Rochester","state":"NY","lat":43.156,"lng":-77.615,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_114/playlist.m3u8"]},
  {"id":"ny-ta-115",  "name":"I-90 Thruway @ Buffalo",         "city":"Buffalo","state":"NY","lat":42.884,"lng":-78.878,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_115/playlist.m3u8"]},
  {"id":"ny-ta-116",  "name":"I-90 Thruway @ Niagara Falls",   "city":"Niagara Falls","state":"NY","lat":43.091,"lng":-78.950,"provider":"NYSDOT Thruway","streams":["https://s58.nysdot.skyvdn.com:443/rtplive/TA_116/playlist.m3u8"]},
  # VIRGINIA
  {"id":"va-mmbt-1",  "name":"I-664 MMBT NB Tunnel Exit",      "city":"Hampton","state":"VA","lat":36.959,"lng":-76.410,"provider":"VDOT Hampton Roads","streams":["https://s16.us-east-1.skyvdn.com:443/rtplive/MMBT1113/playlist.m3u8","https://s15.us-east-1.skyvdn.com:443/rtplive/MMBT1113/playlist.m3u8"]},
  {"id":"va-hr-761",  "name":"I-64 Hampton Roads @ MM 7.6",    "city":"Hampton","state":"VA","lat":37.025,"lng":-76.393,"provider":"VDOT Hampton Roads","streams":["https://s15.us-east-1.skyvdn.com:443/rtplive/HamptonRoads761/playlist.m3u8","https://s16.us-east-1.skyvdn.com:443/rtplive/HamptonRoads761/playlist.m3u8"]},
  {"id":"va-hr-wf104","name":"VA-164 WB Cedar Lane",           "city":"Portsmouth","state":"VA","lat":36.833,"lng":-76.395,"provider":"VDOT Hampton Roads","streams":["https://s17.us-east-1.skyvdn.com:443/rtplive/HamptonRoadsWF104/playlist.m3u8"]},
  {"id":"va-hamp-3",  "name":"Armistead Ave & LaSalle Ave",    "city":"Hampton","state":"VA","lat":37.021,"lng":-76.343,"provider":"City of Hampton","streams":["https://s11.us-east-1.skyvdn.com:443/rtplive/CityofHampton3/playlist.m3u8"]},
  {"id":"va-hamp-6",  "name":"Magruder Blvd & HRCP",           "city":"Hampton","state":"VA","lat":37.062,"lng":-76.374,"provider":"City of Hampton","streams":["https://s11.us-east-1.skyvdn.com:443/rtplive/CityofHampton6/playlist.m3u8"]},
  {"id":"va-hamp-7",  "name":"Mercury Blvd & Armistead Ave",   "city":"Hampton","state":"VA","lat":37.028,"lng":-76.353,"provider":"City of Hampton","streams":["https://s11.us-east-1.skyvdn.com:443/rtplive/CityofHampton7/playlist.m3u8"]},
  {"id":"va-hamp-12", "name":"Coliseum Dr & Convention Ctr",   "city":"Hampton","state":"VA","lat":37.046,"lng":-76.341,"provider":"City of Hampton","streams":["https://s11.us-east-1.skyvdn.com:443/rtplive/CityofHampton12/playlist.m3u8"]},
  {"id":"va-hamp-21", "name":"Coliseum Dr & Cunningham Dr",    "city":"Hampton","state":"VA","lat":37.048,"lng":-76.352,"provider":"City of Hampton","streams":["https://s11.us-east-1.skyvdn.com:443/rtplive/CityofHampton21/playlist.m3u8"]},
  # IOWA
  {"id":"ia-qctv33","name":"I-80 @ Quad Cities Area","city":"Davenport","state":"IA","lat":41.572,"lng":-90.580,"provider":"Iowa DOT","streams":["https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/qctv33qlb/playlist.m3u8"]},
  {"id":"ia-qctv34","name":"I-80 @ Quad Cities West","city":"Davenport","state":"IA","lat":41.570,"lng":-90.598,"provider":"Iowa DOT","streams":["https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/qctv34qlb/playlist.m3u8"]},
  {"id":"ia-dsmtv1","name":"I-35/80 @ Des Moines","city":"Des Moines","state":"IA","lat":41.590,"lng":-93.620,"provider":"Iowa DOT","streams":["https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/dsmtv01/playlist.m3u8"]},
  {"id":"ia-dsmtv2","name":"I-235 @ Des Moines Downtown","city":"Des Moines","state":"IA","lat":41.594,"lng":-93.633,"provider":"Iowa DOT","streams":["https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/dsmtv02/playlist.m3u8"]},
  {"id":"ia-dsmtv3","name":"I-80 @ Des Moines East","city":"Des Moines","state":"IA","lat":41.580,"lng":-93.570,"provider":"Iowa DOT","streams":["https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/dsmtv03/playlist.m3u8"]},
  {"id":"ia-cedarv1","name":"I-380 @ Cedar Rapids","city":"Cedar Rapids","state":"IA","lat":41.977,"lng":-91.668,"provider":"Iowa DOT","streams":["https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/cedartv01/playlist.m3u8"]},
  {"id":"ia-cedarv2","name":"US-30 @ Cedar Rapids West","city":"Cedar Rapids","state":"IA","lat":41.969,"lng":-91.710,"provider":"Iowa DOT","streams":["https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/cedartv02/playlist.m3u8"]},
  {"id":"ia-dsmtv4","name":"I-80 @ Des Moines West","city":"Des Moines","state":"IA","lat":41.588,"lng":-93.710,"provider":"Iowa DOT","streams":["https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/dsmtv04/playlist.m3u8"]},
  {"id":"ia-dsmtv5","name":"I-35 @ Ankeny","city":"Ankeny","state":"IA","lat":41.728,"lng":-93.600,"provider":"Iowa DOT","streams":["https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/dsmtv05/playlist.m3u8"]},
  {"id":"ia-dsmtv6","name":"I-80/35 @ Merle Hay","city":"Des Moines","state":"IA","lat":41.626,"lng":-93.695,"provider":"Iowa DOT","streams":["https://iowadotsfs2.us-east-1.skyvdn.com:443/rtplive/dsmtv06/playlist.m3u8"]},
  # TENNESSEE
  {"id":"tn-nash-1","name":"I-24/40 @ Nashville Downtown","city":"Nashville","state":"TN","lat":36.166,"lng":-86.781,"provider":"TDOT","streams":["https://s1.tdot.skyvdn.com:443/rtplive/tn_nash_001/playlist.m3u8"]},
  {"id":"tn-nash-2","name":"I-65 @ Nashville South","city":"Nashville","state":"TN","lat":36.125,"lng":-86.783,"provider":"TDOT","streams":["https://s1.tdot.skyvdn.com:443/rtplive/tn_nash_002/playlist.m3u8"]},
  {"id":"tn-mem-1","name":"I-40 @ Memphis Downtown","city":"Memphis","state":"TN","lat":35.149,"lng":-90.048,"provider":"TDOT","streams":["https://s2.tdot.skyvdn.com:443/rtplive/tn_mem_001/playlist.m3u8"]},
  {"id":"tn-kx-1","name":"I-40 @ Knoxville Downtown","city":"Knoxville","state":"TN","lat":35.961,"lng":-83.921,"provider":"TDOT","streams":["https://s3.tdot.skyvdn.com:443/rtplive/tn_knox_001/playlist.m3u8"]},
  # GEORGIA
  {"id":"ga-atl-1","name":"I-285 @ Spaghetti Junction NB","city":"Atlanta","state":"GA","lat":33.903,"lng":-84.213,"provider":"GDOT","streams":["https://s1.gdot.skyvdn.com:443/rtplive/ATL001/playlist.m3u8"]},
  {"id":"ga-atl-2","name":"I-75/85 @ Downtown Connector","city":"Atlanta","state":"GA","lat":33.760,"lng":-84.391,"provider":"GDOT","streams":["https://s1.gdot.skyvdn.com:443/rtplive/ATL002/playlist.m3u8"]},
  {"id":"ga-atl-3","name":"I-20 @ Atlanta West","city":"Atlanta","state":"GA","lat":33.748,"lng":-84.468,"provider":"GDOT","streams":["https://s1.gdot.skyvdn.com:443/rtplive/ATL003/playlist.m3u8"]},
  {"id":"ga-atl-4","name":"GA-400 @ Buckhead","city":"Atlanta","state":"GA","lat":33.836,"lng":-84.363,"provider":"GDOT","streams":["https://s1.gdot.skyvdn.com:443/rtplive/ATL004/playlist.m3u8"]},
  # OHIO
  {"id":"oh-col-1","name":"I-70/71 @ Columbus Downtown","city":"Columbus","state":"OH","lat":39.961,"lng":-82.999,"provider":"ODOT","streams":["https://ohtraffic.skyvdn.com:443/rtplive/col001/playlist.m3u8"]},
  {"id":"oh-col-2","name":"I-270 @ Columbus Outer Belt N","city":"Columbus","state":"OH","lat":40.060,"lng":-83.017,"provider":"ODOT","streams":["https://ohtraffic.skyvdn.com:443/rtplive/col002/playlist.m3u8"]},
  {"id":"oh-cle-1","name":"I-90 @ Cleveland Downtown","city":"Cleveland","state":"OH","lat":41.499,"lng":-81.695,"provider":"ODOT","streams":["https://ohtraffic.skyvdn.com:443/rtplive/cle001/playlist.m3u8"]},
  {"id":"oh-cin-1","name":"I-75 @ Cincinnati","city":"Cincinnati","state":"OH","lat":39.103,"lng":-84.512,"provider":"ODOT","streams":["https://ohtraffic.skyvdn.com:443/rtplive/cin001/playlist.m3u8"]},
  # MICHIGAN
  {"id":"mi-det-1","name":"I-75 @ Detroit Ambassador Bridge","city":"Detroit","state":"MI","lat":42.330,"lng":-83.072,"provider":"MDOT","streams":["https://s1.mdot.skyvdn.com:443/rtplive/det001/playlist.m3u8"]},
  {"id":"mi-det-2","name":"I-94 @ Detroit East","city":"Detroit","state":"MI","lat":42.342,"lng":-83.023,"provider":"MDOT","streams":["https://s1.mdot.skyvdn.com:443/rtplive/det002/playlist.m3u8"]},
  {"id":"mi-det-3","name":"I-696 @ Southfield","city":"Southfield","state":"MI","lat":42.490,"lng":-83.222,"provider":"MDOT","streams":["https://s1.mdot.skyvdn.com:443/rtplive/det003/playlist.m3u8"]},
  {"id":"mi-grr-1","name":"US-131 @ Grand Rapids","city":"Grand Rapids","state":"MI","lat":42.966,"lng":-85.670,"provider":"MDOT","streams":["https://s1.mdot.skyvdn.com:443/rtplive/grr001/playlist.m3u8"]},
  # ILLINOIS
  {"id":"il-chi-1","name":"I-90/94 @ Chicago Dan Ryan NB","city":"Chicago","state":"IL","lat":41.837,"lng":-87.626,"provider":"IDOT","streams":["https://s1.idot.skyvdn.com:443/rtplive/chi001/playlist.m3u8"]},
  {"id":"il-chi-2","name":"I-290 @ Chicago Eisenhower","city":"Chicago","state":"IL","lat":41.876,"lng":-87.742,"provider":"IDOT","streams":["https://s1.idot.skyvdn.com:443/rtplive/chi002/playlist.m3u8"]},
  {"id":"il-chi-3","name":"I-294 @ Chicago Tri-State","city":"Rosemont","state":"IL","lat":41.983,"lng":-87.853,"provider":"Illinois Tollway","streams":["https://s2.idot.skyvdn.com:443/rtplive/chi003/playlist.m3u8"]},
  {"id":"il-chi-4","name":"I-88 @ Chicago Aurora","city":"Aurora","state":"IL","lat":41.771,"lng":-88.274,"provider":"Illinois Tollway","streams":["https://s2.idot.skyvdn.com:443/rtplive/chi004/playlist.m3u8"]},
  # TEXAS
  {"id":"tx-hou-1","name":"I-10 @ Houston Katy Freeway EB","city":"Houston","state":"TX","lat":29.762,"lng":-95.369,"provider":"TxDOT","streams":["https://s1.txdot.skyvdn.com:443/rtplive/hou001/playlist.m3u8"]},
  {"id":"tx-hou-2","name":"I-610 @ Houston Inner Loop N","city":"Houston","state":"TX","lat":29.803,"lng":-95.431,"provider":"TxDOT","streams":["https://s1.txdot.skyvdn.com:443/rtplive/hou002/playlist.m3u8"]},
  {"id":"tx-dfw-1","name":"I-35E @ Dallas Downtown","city":"Dallas","state":"TX","lat":32.781,"lng":-96.797,"provider":"TxDOT","streams":["https://s2.txdot.skyvdn.com:443/rtplive/dfw001/playlist.m3u8"]},
  {"id":"tx-dfw-2","name":"I-635 @ LBJ Freeway","city":"Dallas","state":"TX","lat":32.912,"lng":-96.815,"provider":"TxDOT","streams":["https://s2.txdot.skyvdn.com:443/rtplive/dfw002/playlist.m3u8"]},
  {"id":"tx-dfw-3","name":"I-30 @ Fort Worth Downtown","city":"Fort Worth","state":"TX","lat":32.755,"lng":-97.330,"provider":"TxDOT","streams":["https://s2.txdot.skyvdn.com:443/rtplive/dfw003/playlist.m3u8"]},
  {"id":"tx-sat-1","name":"I-35 @ San Antonio Downtown","city":"San Antonio","state":"TX","lat":29.424,"lng":-98.495,"provider":"TxDOT","streams":["https://s3.txdot.skyvdn.com:443/rtplive/sat001/playlist.m3u8"]},
  {"id":"tx-aus-1","name":"I-35 @ Austin Downtown","city":"Austin","state":"TX","lat":30.267,"lng":-97.743,"provider":"TxDOT","streams":["https://s3.txdot.skyvdn.com:443/rtplive/aus001/playlist.m3u8"]},
  # CALIFORNIA
  {"id":"ca-la-1","name":"US-101 @ Hollywood Freeway NB","city":"Los Angeles","state":"CA","lat":34.101,"lng":-118.340,"provider":"Caltrans D7","streams":["https://cwwp2.dot.ca.gov/vm/streamhls/dg_101_los_angeles/playlist.m3u8","https://s1.caltrans.skyvdn.com:443/rtplive/la001/playlist.m3u8"]},
  {"id":"ca-la-2","name":"I-405 @ San Diego Freeway","city":"Los Angeles","state":"CA","lat":33.987,"lng":-118.451,"provider":"Caltrans D7","streams":["https://cwwp2.dot.ca.gov/vm/streamhls/dg_405_los_angeles/playlist.m3u8","https://s1.caltrans.skyvdn.com:443/rtplive/la002/playlist.m3u8"]},
  {"id":"ca-la-3","name":"I-10 @ Santa Monica Freeway","city":"Los Angeles","state":"CA","lat":34.019,"lng":-118.491,"provider":"Caltrans D7","streams":["https://cwwp2.dot.ca.gov/vm/streamhls/dg_010_los_angeles/playlist.m3u8"]},
  {"id":"ca-sf-1","name":"US-101 @ SF Golden Gate","city":"San Francisco","state":"CA","lat":37.808,"lng":-122.478,"provider":"Caltrans D4","streams":["https://cwwp2.dot.ca.gov/vm/streamhls/dg_101_san_francisco/playlist.m3u8","https://s2.caltrans.skyvdn.com:443/rtplive/sf001/playlist.m3u8"]},
  {"id":"ca-sf-2","name":"I-80 @ Bay Bridge WB Approach","city":"San Francisco","state":"CA","lat":37.796,"lng":-122.392,"provider":"Caltrans D4","streams":["https://cwwp2.dot.ca.gov/vm/streamhls/dg_080_san_francisco/playlist.m3u8"]},
  {"id":"ca-sd-1","name":"I-8 @ San Diego Mission Valley","city":"San Diego","state":"CA","lat":32.767,"lng":-117.150,"provider":"Caltrans D11","streams":["https://cwwp2.dot.ca.gov/vm/streamhls/dg_008_san_diego/playlist.m3u8","https://s3.caltrans.skyvdn.com:443/rtplive/sd001/playlist.m3u8"]},
  {"id":"ca-sd-2","name":"I-5 @ San Diego South Bay","city":"San Diego","state":"CA","lat":32.622,"lng":-117.117,"provider":"Caltrans D11","streams":["https://s3.caltrans.skyvdn.com:443/rtplive/sd002/playlist.m3u8"]},
  # FLORIDA
  {"id":"fl-mia-1","name":"I-95 @ Miami Downtown NB","city":"Miami","state":"FL","lat":25.775,"lng":-80.197,"provider":"FDOT D6","streams":["https://s1.fdot.skyvdn.com:443/rtplive/mia001/playlist.m3u8"]},
  {"id":"fl-mia-2","name":"I-195 @ MacArthur Causeway","city":"Miami","state":"FL","lat":25.791,"lng":-80.183,"provider":"FDOT D6","streams":["https://s1.fdot.skyvdn.com:443/rtplive/mia002/playlist.m3u8"]},
  {"id":"fl-orl-1","name":"I-4 @ Orlando Downtown","city":"Orlando","state":"FL","lat":28.542,"lng":-81.379,"provider":"FDOT D5","streams":["https://s2.fdot.skyvdn.com:443/rtplive/orl001/playlist.m3u8"]},
  {"id":"fl-tpa-1","name":"I-275 @ Tampa Howard Frankland","city":"Tampa","state":"FL","lat":27.952,"lng":-82.555,"provider":"FDOT D7","streams":["https://s3.fdot.skyvdn.com:443/rtplive/tpa001/playlist.m3u8"]},
  {"id":"fl-jax-1","name":"I-95 @ Jacksonville Downtown","city":"Jacksonville","state":"FL","lat":30.332,"lng":-81.656,"provider":"FDOT D2","streams":["https://s4.fdot.skyvdn.com:443/rtplive/jax001/playlist.m3u8"]},
  # WASHINGTON
  {"id":"wa-sea-1","name":"I-5 @ Seattle Downtown NB","city":"Seattle","state":"WA","lat":47.609,"lng":-122.335,"provider":"WSDOT","streams":["https://s1.wsdot.skyvdn.com:443/rtplive/sea001/playlist.m3u8"]},
  {"id":"wa-sea-2","name":"I-90 @ Seattle Mt Baker Tunnel","city":"Seattle","state":"WA","lat":47.596,"lng":-122.300,"provider":"WSDOT","streams":["https://s1.wsdot.skyvdn.com:443/rtplive/sea002/playlist.m3u8"]},
  {"id":"wa-sea-3","name":"SR-99 @ Seattle Aurora","city":"Seattle","state":"WA","lat":47.606,"lng":-122.340,"provider":"WSDOT","streams":["https://s1.wsdot.skyvdn.com:443/rtplive/sea003/playlist.m3u8"]},
  {"id":"wa-tac-1","name":"I-5 @ Tacoma Narrows Approach","city":"Tacoma","state":"WA","lat":47.243,"lng":-122.438,"provider":"WSDOT","streams":["https://s2.wsdot.skyvdn.com:443/rtplive/tac001/playlist.m3u8"]},
  # COLORADO
  {"id":"co-den-1","name":"I-25 @ Denver Downtown","city":"Denver","state":"CO","lat":39.740,"lng":-104.987,"provider":"CDOT","streams":["https://s1.cdot.skyvdn.com:443/rtplive/den001/playlist.m3u8"]},
  {"id":"co-den-2","name":"I-70 @ Denver Mousetrap","city":"Denver","state":"CO","lat":39.757,"lng":-104.979,"provider":"CDOT","streams":["https://s1.cdot.skyvdn.com:443/rtplive/den002/playlist.m3u8"]},
  {"id":"co-i70-1","name":"I-70 @ Eisenhower Tunnel","city":"Silverthorne","state":"CO","lat":39.677,"lng":-105.906,"provider":"CDOT","streams":["https://s1.cdot.skyvdn.com:443/rtplive/i70_tunnel/playlist.m3u8"]},
  # ARIZONA
  {"id":"az-phx-1","name":"I-10 @ Phoenix Downtown","city":"Phoenix","state":"AZ","lat":33.448,"lng":-112.074,"provider":"ADOT","streams":["https://s1.adot.skyvdn.com:443/rtplive/phx001/playlist.m3u8"]},
  {"id":"az-phx-2","name":"I-17 @ Phoenix Deck Park","city":"Phoenix","state":"AZ","lat":33.461,"lng":-112.083,"provider":"ADOT","streams":["https://s1.adot.skyvdn.com:443/rtplive/phx002/playlist.m3u8"]},
  {"id":"az-tus-1","name":"I-10 @ Tucson Downtown","city":"Tucson","state":"AZ","lat":32.221,"lng":-110.969,"provider":"ADOT","streams":["https://s2.adot.skyvdn.com:443/rtplive/tus001/playlist.m3u8"]},
  # NEVADA
  {"id":"nv-las-1","name":"I-15 @ Las Vegas Strip","city":"Las Vegas","state":"NV","lat":36.114,"lng":-115.172,"provider":"NDOT","streams":["https://s1.ndot.skyvdn.com:443/rtplive/las001/playlist.m3u8"]},
  {"id":"nv-las-2","name":"US-95 @ Las Vegas Downtown","city":"Las Vegas","state":"NV","lat":36.171,"lng":-115.141,"provider":"NDOT","streams":["https://s1.ndot.skyvdn.com:443/rtplive/las002/playlist.m3u8"]},
  {"id":"nv-ren-1","name":"I-80 @ Reno Downtown","city":"Reno","state":"NV","lat":39.529,"lng":-119.814,"provider":"NDOT","streams":["https://s2.ndot.skyvdn.com:443/rtplive/ren001/playlist.m3u8"]},
  # OREGON
  {"id":"or-pdx-1","name":"I-5 @ Portland Marquam Bridge","city":"Portland","state":"OR","lat":45.510,"lng":-122.669,"provider":"ODOT OR","streams":["https://s1.odot.skyvdn.com:443/rtplive/pdx001/playlist.m3u8"]},
  {"id":"or-pdx-2","name":"I-84 @ Portland Gateway","city":"Portland","state":"OR","lat":45.526,"lng":-122.579,"provider":"ODOT OR","streams":["https://s1.odot.skyvdn.com:443/rtplive/pdx002/playlist.m3u8"]},
  {"id":"or-pdx-3","name":"US-26 @ Portland Sunset Tunnel","city":"Portland","state":"OR","lat":45.525,"lng":-122.724,"provider":"ODOT OR","streams":["https://s1.odot.skyvdn.com:443/rtplive/pdx003/playlist.m3u8"]},
  # NORTH CAROLINA
  {"id":"nc-clt-1","name":"I-277 @ Charlotte Brookshire","city":"Charlotte","state":"NC","lat":35.229,"lng":-80.843,"provider":"NCDOT","streams":["https://s1.ncdot.skyvdn.com:443/rtplive/clt001/playlist.m3u8"]},
  {"id":"nc-clt-2","name":"I-485 @ Charlotte Outer Belt","city":"Charlotte","state":"NC","lat":35.106,"lng":-80.837,"provider":"NCDOT","streams":["https://s1.ncdot.skyvdn.com:443/rtplive/clt002/playlist.m3u8"]},
  {"id":"nc-ral-1","name":"I-40 @ Raleigh Wade Ave","city":"Raleigh","state":"NC","lat":35.793,"lng":-78.688,"provider":"NCDOT","streams":["https://s2.ncdot.skyvdn.com:443/rtplive/ral001/playlist.m3u8"]},
  # MINNESOTA
  {"id":"mn-msp-1","name":"I-35W @ Minneapolis Downtown","city":"Minneapolis","state":"MN","lat":44.973,"lng":-93.270,"provider":"MnDOT","streams":["https://s1.mndot.skyvdn.com:443/rtplive/msp001/playlist.m3u8"]},
  {"id":"mn-msp-2","name":"I-94 @ Minneapolis West","city":"Minneapolis","state":"MN","lat":44.974,"lng":-93.340,"provider":"MnDOT","streams":["https://s1.mndot.skyvdn.com:443/rtplive/msp002/playlist.m3u8"]},
  {"id":"mn-msp-3","name":"I-494 @ Bloomington Strip","city":"Bloomington","state":"MN","lat":44.857,"lng":-93.330,"provider":"MnDOT","streams":["https://s1.mndot.skyvdn.com:443/rtplive/msp003/playlist.m3u8"]},
  # MASSACHUSETTS
  {"id":"ma-bos-1","name":"I-93 @ Boston Big Dig NB","city":"Boston","state":"MA","lat":42.357,"lng":-71.059,"provider":"MassDOT","streams":["https://s1.massdot.skyvdn.com:443/rtplive/bos001/playlist.m3u8"]},
  {"id":"ma-bos-2","name":"I-90 @ Boston Mass Pike EB","city":"Boston","state":"MA","lat":42.350,"lng":-71.075,"provider":"MassDOT","streams":["https://s1.massdot.skyvdn.com:443/rtplive/bos002/playlist.m3u8"]},
  {"id":"ma-bos-3","name":"I-93 @ Boston Expressway SB","city":"Boston","state":"MA","lat":42.333,"lng":-71.056,"provider":"MassDOT","streams":["https://s1.massdot.skyvdn.com:443/rtplive/bos003/playlist.m3u8"]},
  # PENNSYLVANIA
  {"id":"pa-phi-1","name":"I-95 @ Philadelphia Delaware Expwy","city":"Philadelphia","state":"PA","lat":39.963,"lng":-75.145,"provider":"PennDOT","streams":["https://s1.penndot.skyvdn.com:443/rtplive/phi001/playlist.m3u8"]},
  {"id":"pa-phi-2","name":"I-76 @ Philadelphia Schuylkill","city":"Philadelphia","state":"PA","lat":39.961,"lng":-75.194,"provider":"PennDOT","streams":["https://s1.penndot.skyvdn.com:443/rtplive/phi002/playlist.m3u8"]},
  {"id":"pa-pit-1","name":"I-376 @ Pittsburgh Downtown","city":"Pittsburgh","state":"PA","lat":40.441,"lng":-80.007,"provider":"PennDOT","streams":["https://s2.penndot.skyvdn.com:443/rtplive/pit001/playlist.m3u8"]},
  # MARYLAND
  {"id":"md-blt-1","name":"I-695 @ Baltimore Beltway N","city":"Baltimore","state":"MD","lat":39.371,"lng":-76.623,"provider":"MDSHA","streams":["https://s1.mdshatraffic.skyvdn.com:443/rtplive/blt001/playlist.m3u8"]},
  {"id":"md-blt-2","name":"I-95 @ Baltimore Fort McHenry","city":"Baltimore","state":"MD","lat":39.263,"lng":-76.599,"provider":"MDSHA","streams":["https://s1.mdshatraffic.skyvdn.com:443/rtplive/blt002/playlist.m3u8"]},
  # NEW JERSEY
  {"id":"nj-nwk-1","name":"NJ Tpk @ Newark Exit 13A","city":"Newark","state":"NJ","lat":40.734,"lng":-74.177,"provider":"NJTA","streams":["https://s1.njdot.skyvdn.com:443/rtplive/nwk001/playlist.m3u8"]},
  {"id":"nj-gsp-1","name":"Garden State Pkwy @ Paramus","city":"Paramus","state":"NJ","lat":40.945,"lng":-74.074,"provider":"NJTA","streams":["https://s1.njdot.skyvdn.com:443/rtplive/gsp001/playlist.m3u8"]},
  {"id":"nj-acx-1","name":"AC Expressway @ Atlantic City","city":"Atlantic City","state":"NJ","lat":39.364,"lng":-74.423,"provider":"SJTA","streams":["https://s2.njdot.skyvdn.com:443/rtplive/acx001/playlist.m3u8"]},
  # CONNECTICUT
  {"id":"ct-hfd-1","name":"I-84 @ Hartford Downtown","city":"Hartford","state":"CT","lat":41.764,"lng":-72.683,"provider":"ConnDOT","streams":["https://s1.ctdot.skyvdn.com:443/rtplive/hfd001/playlist.m3u8"]},
  {"id":"ct-nhv-1","name":"I-95 @ New Haven Q Bridge","city":"New Haven","state":"CT","lat":41.296,"lng":-72.921,"provider":"ConnDOT","streams":["https://s1.ctdot.skyvdn.com:443/rtplive/nhv001/playlist.m3u8"]},
  # INDIANA
  {"id":"in-ind-1","name":"I-70 @ Indianapolis Downtown","city":"Indianapolis","state":"IN","lat":39.768,"lng":-86.158,"provider":"INDOT","streams":["https://indot.skyvdn.com:443/rtplive/ind001/playlist.m3u8"]},
  {"id":"in-ind-2","name":"I-465 @ Indianapolis Outer Belt N","city":"Indianapolis","state":"IN","lat":39.908,"lng":-86.155,"provider":"INDOT","streams":["https://indot.skyvdn.com:443/rtplive/ind002/playlist.m3u8"]},
  # MISSOURI
  {"id":"mo-stl-1","name":"I-70 @ St. Louis Poplar St Bridge","city":"St. Louis","state":"MO","lat":38.630,"lng":-90.189,"provider":"MoDOT","streams":["https://s1.modot.skyvdn.com:443/rtplive/stl001/playlist.m3u8"]},
  {"id":"mo-kci-1","name":"I-70 @ Kansas City Downtown","city":"Kansas City","state":"MO","lat":39.097,"lng":-94.579,"provider":"MoDOT","streams":["https://s2.modot.skyvdn.com:443/rtplive/kci001/playlist.m3u8"]},
  # WISCONSIN
  {"id":"wi-mil-1","name":"I-43 @ Milwaukee Downtown","city":"Milwaukee","state":"WI","lat":43.040,"lng":-87.910,"provider":"WisDOT","streams":["https://s1.wisdot.skyvdn.com:443/rtplive/mil001/playlist.m3u8"]},
  {"id":"wi-mil-2","name":"I-894 @ Milwaukee Bypass","city":"Milwaukee","state":"WI","lat":43.008,"lng":-88.009,"provider":"WisDOT","streams":["https://s1.wisdot.skyvdn.com:443/rtplive/mil002/playlist.m3u8"]},
  # LOUISIANA
  {"id":"la-nor-1","name":"I-10 @ New Orleans Superdome","city":"New Orleans","state":"LA","lat":29.951,"lng":-90.081,"provider":"LADOTD","streams":["https://s1.ladotd.skyvdn.com:443/rtplive/nor001/playlist.m3u8"]},
  {"id":"la-nor-2","name":"I-610 @ New Orleans Inner Loop","city":"New Orleans","state":"LA","lat":29.985,"lng":-90.075,"provider":"LADOTD","streams":["https://s1.ladotd.skyvdn.com:443/rtplive/nor002/playlist.m3u8"]},
  {"id":"la-bat-1","name":"I-10 @ Baton Rouge Downtown","city":"Baton Rouge","state":"LA","lat":30.449,"lng":-91.188,"provider":"LADOTD","streams":["https://s2.ladotd.skyvdn.com:443/rtplive/bat001/playlist.m3u8"]},
  # UTAH
  {"id":"ut-slc-1","name":"I-15 @ Salt Lake City Center","city":"Salt Lake City","state":"UT","lat":40.760,"lng":-111.891,"provider":"UDOT","streams":["https://s1.udot.skyvdn.com:443/rtplive/slc001/playlist.m3u8"]},
  {"id":"ut-slc-2","name":"I-80 @ Salt Lake City East","city":"Salt Lake City","state":"UT","lat":40.761,"lng":-111.833,"provider":"UDOT","streams":["https://s1.udot.skyvdn.com:443/rtplive/slc002/playlist.m3u8"]},
  # REMAINING STATES
  {"id":"ks-wic-1","name":"I-135 @ Wichita Downtown","city":"Wichita","state":"KS","lat":37.686,"lng":-97.336,"provider":"KDOT","streams":["https://s1.kdot.skyvdn.com:443/rtplive/wic001/playlist.m3u8"]},
  {"id":"ok-okc-1","name":"I-35 @ Oklahoma City Downtown","city":"Oklahoma City","state":"OK","lat":35.467,"lng":-97.516,"provider":"ODOT OK","streams":["https://s1.odot-ok.skyvdn.com:443/rtplive/okc001/playlist.m3u8"]},
  {"id":"ok-tul-1","name":"I-44 @ Tulsa Downtown","city":"Tulsa","state":"OK","lat":36.154,"lng":-95.994,"provider":"ODOT OK","streams":["https://s2.odot-ok.skyvdn.com:443/rtplive/tul001/playlist.m3u8"]},
  {"id":"sc-col-1","name":"I-26 @ Columbia Downtown","city":"Columbia","state":"SC","lat":34.000,"lng":-81.035,"provider":"SCDOT","streams":["https://s1.scdot.skyvdn.com:443/rtplive/col001/playlist.m3u8"]},
  {"id":"sc-chs-1","name":"I-26 @ Charleston","city":"Charleston","state":"SC","lat":32.799,"lng":-79.934,"provider":"SCDOT","streams":["https://s2.scdot.skyvdn.com:443/rtplive/chs001/playlist.m3u8"]},
  {"id":"al-bhm-1","name":"I-65 @ Birmingham Downtown","city":"Birmingham","state":"AL","lat":33.519,"lng":-86.811,"provider":"ALDOT","streams":["https://s1.aldot.skyvdn.com:443/rtplive/bhm001/playlist.m3u8"]},
  {"id":"al-mob-1","name":"I-65 @ Mobile I-10 Junction","city":"Mobile","state":"AL","lat":30.692,"lng":-88.043,"provider":"ALDOT","streams":["https://s2.aldot.skyvdn.com:443/rtplive/mob001/playlist.m3u8"]},
  {"id":"ms-jkn-1","name":"I-55 @ Jackson Downtown","city":"Jackson","state":"MS","lat":32.299,"lng":-90.185,"provider":"MDOT MS","streams":["https://s1.mdot-ms.skyvdn.com:443/rtplive/jkn001/playlist.m3u8"]},
  {"id":"ar-lrk-1","name":"I-30 @ Little Rock Downtown","city":"Little Rock","state":"AR","lat":34.746,"lng":-92.289,"provider":"ArDOT","streams":["https://s1.ardot.skyvdn.com:443/rtplive/lrk001/playlist.m3u8"]},
  {"id":"ky-lou-1","name":"I-71/64 @ Louisville Spaghetti Jct","city":"Louisville","state":"KY","lat":38.255,"lng":-85.758,"provider":"KYTC","streams":["https://s1.kytc.skyvdn.com:443/rtplive/lou001/playlist.m3u8"]},
  {"id":"ky-lex-1","name":"I-75 @ Lexington Downtown","city":"Lexington","state":"KY","lat":38.046,"lng":-84.497,"provider":"KYTC","streams":["https://s2.kytc.skyvdn.com:443/rtplive/lex001/playlist.m3u8"]},
  {"id":"wv-chs-1","name":"I-64/77 @ Charleston Downtown","city":"Charleston","state":"WV","lat":38.350,"lng":-81.633,"provider":"WVDOH","streams":["https://s1.wvdoh.skyvdn.com:443/rtplive/chs001/playlist.m3u8"]},
  {"id":"ne-oma-1","name":"I-80 @ Omaha Downtown","city":"Omaha","state":"NE","lat":41.258,"lng":-95.938,"provider":"NDOR","streams":["https://s1.ndor.skyvdn.com:443/rtplive/oma001/playlist.m3u8"]},
  {"id":"sd-sxf-1","name":"I-29 @ Sioux Falls Downtown","city":"Sioux Falls","state":"SD","lat":43.549,"lng":-96.730,"provider":"SDDOT","streams":["https://s1.sddot.skyvdn.com:443/rtplive/sxf001/playlist.m3u8"]},
  {"id":"nd-bis-1","name":"I-94 @ Bismarck Downtown","city":"Bismarck","state":"ND","lat":46.808,"lng":-100.784,"provider":"NDDOT","streams":["https://s1.nddot.skyvdn.com:443/rtplive/bis001/playlist.m3u8"]},
  {"id":"mt-bil-1","name":"I-90 @ Billings Downtown","city":"Billings","state":"MT","lat":45.783,"lng":-108.501,"provider":"MDT","streams":["https://s1.mdt.skyvdn.com:443/rtplive/bil001/playlist.m3u8"]},
  {"id":"id-boi-1","name":"I-84 @ Boise Downtown","city":"Boise","state":"ID","lat":43.614,"lng":-116.202,"provider":"ITD","streams":["https://s1.itd.skyvdn.com:443/rtplive/boi001/playlist.m3u8"]},
  {"id":"nm-abq-1","name":"I-25 @ Albuquerque Downtown","city":"Albuquerque","state":"NM","lat":35.085,"lng":-106.651,"provider":"NMDOT","streams":["https://s1.nmdot.skyvdn.com:443/rtplive/abq001/playlist.m3u8"]},
  {"id":"wy-cas-1","name":"I-25 @ Casper Downtown","city":"Casper","state":"WY","lat":42.866,"lng":-106.313,"provider":"WYDOT","streams":["https://s1.wydot.skyvdn.com:443/rtplive/cas001/playlist.m3u8"]},
  {"id":"hi-hnl-1","name":"H-1 @ Honolulu Downtown","city":"Honolulu","state":"HI","lat":21.306,"lng":-157.858,"provider":"HDOT","streams":["https://s1.hdot.skyvdn.com:443/rtplive/hnl001/playlist.m3u8"]},
  {"id":"ak-anc-1","name":"Glenn Hwy @ Anchorage Muldoon","city":"Anchorage","state":"AK","lat":61.214,"lng":-149.762,"provider":"Alaska DOT","streams":["https://s1.akdot.skyvdn.com:443/rtplive/anc001/playlist.m3u8"]},
]

STATUS_FILE = Path(__file__).parent / "camera_status.json"
LOG_FILE    = Path(__file__).parent / "camera_terminal.log"
_log_lines: list = []
_log_fh = None

def ts():   return datetime.datetime.now().strftime("%H:%M:%S")
def now_iso(): return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def tlog(msg: str, level: str = "info") -> None:
    global _log_lines
    colour = {"sys":DIM+CYAN,"info":GREEN,"new":BOLD+GREEN,"warn":YELLOW,"err":RED,"dim":DIM,"scan":CYAN}.get(level, WHITE)
    line = f"[{ts()}] {msg}"
    print(f"{colour}{line}{RESET}", flush=True)
    _log_lines.append(line)
    if len(_log_lines) > MAX_LOG_LINES:
        _log_lines = _log_lines[-MAX_LOG_LINES:]
    if _log_fh:
        try: _log_fh.write(line + "\n"); _log_fh.flush()
        except Exception: pass

def divider(): tlog("─" * 56, "dim")

def check_camera(cam: dict, timeout: int = 5) -> dict:
    streams = cam.get("streams", [])
    for idx, url in enumerate(streams):
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "NWSRadar-CamTerminal/2.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                latency = int((time.monotonic() - t0) * 1000)
                if resp.status == 200:
                    return {"id":cam["id"],"status":"live","stream_idx":idx,"http_code":200,"latency_ms":latency,"error":None,"active_url":url}
                err = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e: err = f"HTTP {e.code}"
        except Exception as e: err = str(e)[:60]
        next_idx = idx + 1
        if next_idx < len(streams):
            tlog(f"⚠ OFFLINE  {cam['id']} — {cam['name']} has gone offline, switching to stream {next_idx+1}...", "warn")
        else:
            tlog(f"✖ DEAD     {cam['id']} — {cam['name']} — all {len(streams)} stream(s) exhausted.", "err")
    return {"id":cam["id"],"status":"offline","stream_idx":-1,"http_code":None,"latency_ms":None,"error":"all exhausted","active_url":None}

def run_scan(cameras: list) -> dict:
    divider()
    tlog(f"SCAN: Checking {len(cameras)} HLS stream(s)...", "sys")
    divider()
    results, live_count, dead_count = [], 0, 0
    for cam in cameras:
        result = check_camera(cam)
        results.append({**cam, **result})
        if result["status"] == "live":
            live_count += 1
            si = result["stream_idx"]
            label = f"[stream {si+1}/{len(cam['streams'])}{'  (failover)' if si>0 else ''}]"
            tlog(f"LIVE ✓  {cam['id']:20s} — {cam['name'][:40]:40s} {label}  ({result['latency_ms']}ms)", "new")
        else:
            dead_count += 1
    divider()
    live_pct = int(live_count / max(len(cameras),1) * 100)
    tlog(f"SUMMARY: {live_count}/{len(cameras)} LIVE ({live_pct}%)  |  {dead_count} offline", "sys")
    divider()
    doc = {"updated":now_iso(),"total":len(cameras),"live":live_count,"offline":dead_count,"live_pct":live_pct,"cameras":results,"log_tail":_log_lines[-100:]}
    try: STATUS_FILE.write_text(json.dumps(doc, indent=2), encoding="utf-8"); tlog(f"SYS: Status → {STATUS_FILE.name}", "sys")
    except Exception as e: tlog(f"SYS: Status write failed: {e}", "warn")
    return doc

def print_banner(cameras, args):
    states = sorted({c["state"] for c in cameras})
    total_streams = sum(len(c["streams"]) for c in cameras)
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗
║    ⬡  NWS RADAR — TRAFFIC CAMERA FEED TERMINAL  v2       ║
╚══════════════════════════════════════════════════════════╝{RESET}
  {DIM}Cameras      : {WHITE}{len(cameras)}{RESET}
  {DIM}Total streams: {WHITE}{total_streams} (failover enabled){RESET}
  {DIM}States       : {WHITE}{', '.join(states)}{RESET}
  {DIM}Interval     : {WHITE}{args.interval}s{RESET}
  {DIM}Log          : {WHITE}{args.log}{RESET}
  {DIM}Status JSON  : {WHITE}{STATUS_FILE}{RESET}
  {DIM}Mode         : {WHITE}{'Single scan' if args.once else 'Continuous — terminal never resets'}{RESET}
""")

def parse_args():
    p = argparse.ArgumentParser(description="NWS Radar — Traffic Camera Feed Terminal v2", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--once",     action="store_true",  help="Run one scan then exit")
    p.add_argument("--interval", type=int, default=30, help="Scan interval in seconds (default: 30)")
    p.add_argument("--state",    type=str, default=None, help="Filter to state code (NY, TX, CA...)")
    p.add_argument("--open",     action="store_true",  help="Open index.html in browser on start")
    p.add_argument("--log",      type=str, default=str(LOG_FILE), help="Log file path (appended, never cleared)")
    p.add_argument("--timeout",  type=int, default=5,  help="HTTP timeout per stream in seconds")
    return p.parse_args()

def main():
    global _log_fh
    args    = parse_args()
    cameras = TRAFFIC_CAMERAS
    if args.state:
        cameras = [c for c in cameras if c["state"].upper() == args.state.upper()]
        if not cameras:
            print(f"{RED}No cameras for '{args.state}'. Available: {sorted({c['state'] for c in TRAFFIC_CAMERAS})}{RESET}")
            sys.exit(1)
    if args.log:
        try: _log_fh = open(args.log, "a", encoding="utf-8")
        except Exception as e: print(f"{YELLOW}[WARN] Cannot open log: {e}{RESET}")
    if sys.platform == "win32": os.system("")
    print_banner(cameras, args)
    if args.open:
        html = Path(__file__).parent / "index.html"
        if html.exists(): webbrowser.open(html.as_uri()); tlog(f"SYS: Opened {html.name} in browser.", "sys")
        else: tlog("SYS: index.html not found.", "warn")
    tlog(f"SYS: Camera terminal v2 started — {len(cameras)} cameras, {sum(len(c['streams']) for c in cameras)} streams.", "sys")
    tlog("SYS: Terminal is persistent — log never resets.", "sys")
    scan_n = 0
    try:
        while True:
            scan_n += 1
            tlog(f"SYS: ═══ Scan #{scan_n} @ {now_iso()} ═══", "scan")
            run_scan(cameras)
            if args.once: break
            tlog(f"SYS: Next scan in {args.interval}s. Ctrl+C to quit.", "sys")
            time.sleep(args.interval)
    except KeyboardInterrupt: tlog("\nSYS: Stopped by user. Log preserved.", "sys")
    finally:
        if _log_fh: _log_fh.close()

if __name__ == "__main__":
    main()
