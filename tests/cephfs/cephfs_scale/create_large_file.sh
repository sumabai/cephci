#!/bin/bash

# Define the size of the file in bytes (100GB)
size=10
file_size=$((size * 1024 * 1024 * 1024))
echo "File size in bytes: $file_size"

# Get the hostname
hostname=$(hostname)

# Get the subvolume name from the mount path
mount_path=$1
subvolume_name=$(basename ${mount_path})

# Record the start time
start_time=$(date +%s)

# Generate random content to fill the file in the mount path directory
base64 /dev/urandom | head -c $file_size > "${mount_path}/large_file_${hostname}_${subvolume_name}_${size}GB.txt"

# Record the end time
end_time=$(date +%s)

# Calculate the time taken
time_taken=$((end_time - start_time))

echo "File ${mount_path}/large_file_${hostname}_${subvolume_name}_${size}GB.txt creation complete. Time taken: $time_taken seconds."

echo "Large file creation complete."
