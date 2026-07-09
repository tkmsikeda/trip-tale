FROM public.ecr.aws/lambda/python:3.13

RUN dnf update -y && \
    dnf install -y \
        gcc \
        gcc-c++ \
        git \
        make \
        cmake \
        nasm \
        yasm \
        tar \
        xz \
        pkgconf-pkg-config

WORKDIR /tmp

# x264
RUN git clone --depth 1 https://code.videolan.org/videolan/x264.git

WORKDIR /tmp/x264

RUN ./configure \
        --prefix=/usr/local \
        --enable-static \
        --disable-opencl && \
    make -j$(nproc) && \
    make install

# FFmpeg
WORKDIR /tmp

RUN curl -LO https://ffmpeg.org/releases/ffmpeg-6.1.6.tar.xz && \
    tar xf ffmpeg-6.1.6.tar.xz

WORKDIR /tmp/ffmpeg-6.1.6

RUN PKG_CONFIG_PATH=/usr/local/lib/pkgconfig \
    ./configure \
        --prefix=/usr/local \
        --enable-gpl \
        --enable-libx264 \
        --extra-cflags="-I/usr/local/include" \
        --extra-ldflags="-L/usr/local/lib"

RUN make -j$(nproc)

RUN make install