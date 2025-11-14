$PROTO_DIR = "protos"
$OUT_DIR = "src/server"

if (!(Test-Path $OUT_DIR)) {
    New-Item -ItemType Directory -Path $OUT_DIR | Out-Null
}

python -m grpc_tools.protoc `
    -I $PROTO_DIR `
    --python_out=$OUT_DIR `
    --grpc_python_out=$OUT_DIR `
    train_booking.proto

$OUT_DIR = "src/client"

if (!(Test-Path $OUT_DIR)) {
    New-Item -ItemType Directory -Path $OUT_DIR | Out-Null
}

python -m grpc_tools.protoc `
    -I $PROTO_DIR `
    --python_out=$OUT_DIR `
    --grpc_python_out=$OUT_DIR `
    train_booking.proto

$OUT_DIR = "."

if (!(Test-Path $OUT_DIR)) {
    New-Item -ItemType Directory -Path $OUT_DIR | Out-Null
}

python -m grpc_tools.protoc `
    -I $PROTO_DIR `
    --python_out=$OUT_DIR `
    --grpc_python_out=$OUT_DIR `
    train_booking.proto