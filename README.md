# Research Information Retrieval System

This project provides a chatbot-based system for retrieving and storing information from two main sources:
1. FDA (Food and Drug Administration) data
2. Academic papers

## Features

### FDA Data Retrieval
The system can retrieve and store various types of FDA information:
- **Recalls**: Food and product recalls, safety alerts
- **Drugs**: Drug safety information and adverse events
- **Food Safety**: Food-related safety information
- **Clinical Data**: Clinical trial and drug event information

Data is organized in the following structure:
```
fda_data/
    recalls/
        fda_info.json
    drugs/
        fda_info.json
    food/
        fda_info.json
    clinical/
        fda_info.json
```

### Academic Papers
The system can search and store academic papers using the arXiv API:
- Search papers by topic
- Extract paper metadata
- Store paper information including:
  - Title
  - Authors
  - Summary
  - Publication date
  - PDF URL

Papers are organized by topic in:
```
papers/
    {topic_name}/
        papers_info.json
```

## Usage

### FDA Data Search
```python
from research_server import search_fda

# Search for different types of FDA information
search_fda("recalls")    # Search recall information
search_fda("drugs")      # Search drug information
search_fda("food")       # Search food safety information
search_fda("clinical")   # Search clinical data
```

### Academic Paper Search
```python
from research_server import search_papers

# Search for papers on a specific topic
search_papers("machine learning", max_results=5)
```

### Viewing Stored Information
The system provides resource endpoints to view stored information:
- `fda://{topic}` - View FDA information for a specific topic
- `papers://{topic}` - View stored papers for a specific topic

## Data Storage
- All FDA data is stored in JSON format under the `fda_data` directory
- Academic paper information is stored in JSON format under the `papers` directory
- Each topic/type has its own subdirectory for better organization
- Data is saved atomically to prevent corruption

## Features
- Semantic search capabilities
- Structured data storage
- Atomic file operations for data safety
- Support for multiple FDA data types
- Academic paper metadata extraction
- Topic-based organization
