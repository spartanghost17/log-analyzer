# Synaps (AI driven and statistical log Analyser)

# How to use

This will build deploy the entire project's infrastructure

```bash
make rebuild-all
```

> Important note make sure to pull a specific ollama model

```bash
~$ docker exec -it ollama sh
~$ ollama pull deepseek-coder:6.7b # this can be any model please check smaller LLM models online
~$ ollama list
# ollama list installed models
NAME                   ID              SIZE      MODIFIED
deepseek-coder:6.7b    ce298d984115    3.8 GB    2 days ago
```

# Screens

## 1. Main dashboard

Here you can see the you can the live ingestion dashboard with metrics about log ingestion
![Dashboard-screen](documentation/images/1-dashboard-screen.png)

## 2. Data cortex (granular live logs)

Data cortex - the second screen show live information about what kind of logs are coming into the system
![Data-cortex-screen](documentation/images/2-data-cortex-screen.png)

## 3. Cognitive search (semantic search)

Semantic search looks for logs based on key words and patterns and clusters them based on pattern, services, error level, etc.

![Cognitive-search-screen](documentation/images/3-1-congitive-search.png)

### 3.1. Expanded log group

Below you can see what the information is contained within a log group, like how many logs share the pattern, the similarity score, the error level and even the range of time these logs cover

![clicked-log-group-1](documentation/images/3-2-cognitive-search-modal-one.png)
![clicked-log-group-3](documentation/images/3-4-cognitive-search-modal-three.png)

Finally you can investigate a specific log and in the clustered group and see all the full information about the log (from environment name, to podname, stacktraces, etc.)

![clicked-log-group-2](documentation/images/3-3-cognitive-search-modal-two.png)

## 4. Insight pathway (report analysis)

The system generated analysis report (24 hours) that generated a summary of logs, root cause and potential fixes. It also provides a z-score anomaly dectection dashboard that covers the 24 hours period.

![analysis-report-1](documentation/images/4-1-analysis-report-part-one.png)
![analysis-report-2](documentation/images/4-2-analysis-report-part-two.png)

Expend report information shows the different statistics about information analysed during that period, such as total logs, how many logs at each level levels, the report generation time, the model used with token count, the recommendations, etc.

![analysis-report-3](documentation/images/4-3-analysis-report-modal-part-one.png)
![analysis-report-4](documentation/images/4-4-analysis-report-modal-part-two.png)
![analysis-report-5](documentation/images/4-5-analysis-report-modal-part-three.png)

## 5. Metrics (anomaly detection & alerts)

Filtering the different anomaly reports and analysis

![metrics](documentation/images/5-anomaly-detection-alerts-screen.png)

## 6. Topology (system architecture)

Shows flow of data for the system architecture

![architecture](documentation/images/6-topology-screen.png)
