FROM public.ecr.aws/lambda/python:3.13

COPY --from=trip-tale-ffmpeg /usr/local /usr/local

# 必要ならPATHを設定
ENV PATH="/usr/local/bin:${PATH}"
ENV LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH}"

# Lambda Task Root にコピー
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# 依存パッケージをインストール
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Lambda 関数をコピー
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

# ハンドラーを指定
CMD ["lambda_function.lambda_handler"]
