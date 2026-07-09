FROM public.ecr.aws/lambda/python:3.13

COPY --from=trip-tale-ffmpeg /usr/local /usr/local

# 必要ならPATHを設定
ENV PATH="/usr/local/bin:${PATH}"
ENV LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH}"

# 必要なツールをインストール
# RUN yum install -y tar xz curl gcc make

# # ffmpeg 6.1.6 をダウンロードしてコンパイル
# RUN curl -L https://ffmpeg.org/releases/ffmpeg-6.1.6.tar.xz -o /tmp/ffmpeg-6.1.6.tar.xz && \
#     tar -xf /tmp/ffmpeg-6.1.6.tar.xz -C /tmp && \
#     cd /tmp/ffmpeg-6.1.6 && \
#     ./configure --prefix=/usr/local --disable-x86asm && \
#     make && \
#     make install && \
#     rm -rf /tmp/ffmpeg*

# Lambda Task Root にコピー
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# 依存パッケージをインストール
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Lambda 関数をコピー
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

# ハンドラーを指定
CMD ["lambda_function.lambda_handler"]
