#!/bin/bash

 # Start all test servers
  ./tmp/test.sh start

  # Run every sentinel command against all test targets
  ./tmp/test.sh run

  # Full automated cycle (start → test → stop)
  ./tmp/test.sh all

  # Check if servers are up                                                                                             
  ./tmp/test.sh status
  
  # Kill everything                                                                                                     
  ./tmp/test.sh stop