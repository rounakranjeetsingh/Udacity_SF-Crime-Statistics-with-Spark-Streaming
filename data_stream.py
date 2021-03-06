import logging
import json
from pyspark.sql import SparkSession
from pyspark.sql.types import *
import pyspark.sql.functions as psf

# TODO Create a schema for incoming resources
schema = StructType([
    StructField('crime_id', StringType(), True),
    StructField('original_crime_type_name', StringType(), True),
    StructField('report_date', StringType(), True),
    StructField('call_date', StringType(), True),
    StructField('offense_date', StringType(), True),
    StructField('call_time', StringType(), True),
    StructField('call_date_time', TimestampType(), True),
    StructField('disposition', StringType(), True),
    StructField('address', StringType(), True),
    StructField('city', StringType(), True),
    StructField('state', StringType(), True),
    StructField('agency_id', StringType(), True),
    StructField('address_type', StringType(), True),
    StructField('common_location', StringType(), True)
])


def run_spark_job(spark):
    # Create Spark Configuration
    # Create Spark configurations with max offset of 200 per trigger
    # set up correct bootstrap server and port
    df = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "localhost:9092") \
        .option("subscribe", "com.udacity.crime.statistics.LA") \
        .option("startingOffsets", "earliest") \
        .option("maxOffsetsPerTrigger", 2000) \
        .option("stopGracefullyOnShutDown", "true") \
        .option("maxRatePerPartition", 1000) \
        .load()

    # Show schema for the incoming resources for checks
    #df.printSchema()

    # Extract the correct column from the kafka input resources
    # Take only value and convert it to String
    kafka_df = df.selectExpr("CAST(value as STRING)")

    service_table = kafka_df \
        .select(psf.from_json(psf.col('value'), schema).alias("crime-statistics")) \
        .select("crime-statistics.*")

    #service_table.printSchema()

    # Select original_crime_type_name and disposition
    distinct_table = service_table \
        .select('original_crime_type_name',
                'disposition',
                'call_date_time') \
        .withWatermark('call_date_time', '60 minutes')

    #distinct_table.printSchema()

    # count the number of original crime type
    agg_df = distinct_table \
        .groupBy('original_crime_type_name', psf.window('call_date_time', '60 minutes')) \
        .count()

    #agg_df.printSchema()

    # TODO Q1. Submit a screen shot of a batch ingestion of the aggregation
    # TODO write output stream
    query = agg_df \
        .writeStream \
        .format('console') \
        .outputMode('Complete') \
        .start()

    # Attach a ProgressReporter
    query.awaitTermination()

    # TODO get the right radio code json path
    radio_code_json_filepath = "radio_code.json"
    radio_code_df = spark.read.json(radio_code_json_filepath)

    # clean up your data so that the column names match on radio_code_df and agg_df
    # we will want to join on the disposition code

    # TODO rename disposition_code column to disposition
    radio_code_df = radio_code_df.withColumnRenamed("disposition_code", "disposition")

    # TODO join on disposition column
    join_query = agg_df \
        .join(radio_code_df, on='disposition', how='inner')

    join_query_writer = join_query \
        .writeStream \
        .format('console') \
        .outputMode('append') \
        .start()

    join_query_writer.awaitTermination()


if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.DEBUG)
    console = logging.StreamHandler()
    logger.addHandler(console)

    # TODO Create Spark in Standalone mode
    spark = SparkSession \
        .builder \
        .master("local[*]") \
        .appName("KafkaSparkStructuredStreaming") \
        .config("spark.ui.port", 3000) \
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")
    logger.info("Spark started")

    run_spark_job(spark)

    spark.stop()