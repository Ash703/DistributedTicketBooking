#!/bin/bash
# Compile .proto files into Python gRPC classes
# Output goes directly into ./generated (no nested protos/ folder)

PROTO_DIR=./protos
OUT_DIR=./src/server

# Create output dir if it doesn't exist
mkdir -p $OUT_DIR

# Run protoc
python -m grpc_tools.protoc \
    -I $PROTO_DIR \
    --python_out=$OUT_DIR \
    --grpc_python_out=$OUT_DIR \
    train_booking.proto


OUT_DIR=./src/client

# Create output dir if it doesn't exist
mkdir -p $OUT_DIR

# Run protoc
python -m grpc_tools.protoc \
    -I $PROTO_DIR \
    --python_out=$OUT_DIR \
    --grpc_python_out=$OUT_DIR \
    train_booking.proto

OUT_DIR=./

# Create output dir if it doesn't exist
mkdir -p $OUT_DIR

# Run protoc
python -m grpc_tools.protoc \
    -I $PROTO_DIR \
    --python_out=$OUT_DIR \
    --grpc_python_out=$OUT_DIR \
    train_booking.proto