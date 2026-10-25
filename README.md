# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/Meilocora/Application_Agent/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                     |    Stmts |     Miss |   Cover |   Missing |
|----------------------------------------- | -------: | -------: | ------: | --------: |
| src/application\_agent/\_\_init\_\_.py   |      103 |       82 |     20% |31-87, 91-95, 100-123, 128-129, 134-136, 141-142, 147-155 |
| src/application\_agent/arbeitsagentur.py |       41 |        0 |    100% |           |
| src/application\_agent/commute.py        |       49 |       36 |     27% |29-33, 37, 44-62, 69-90 |
| src/application\_agent/config.py         |       16 |        0 |    100% |           |
| src/application\_agent/context.py        |       10 |        4 |     60% |     20-23 |
| src/application\_agent/documents.py      |      128 |      106 |     17% |28-36, 41-51, 56-71, 83-115, 125-130, 135-171, 178-198 |
| src/application\_agent/export.py         |       57 |       40 |     30% |40-43, 64-117 |
| src/application\_agent/geo.py            |       10 |        6 |     40% |     12-22 |
| src/application\_agent/job\_agents.py    |       14 |        3 |     79% |     24-27 |
| src/application\_agent/letters.py        |       27 |       19 |     30% |12, 16-17, 27-62 |
| src/application\_agent/matching.py       |       34 |       21 |     38% |26-28, 37-38, 53-56, 64-79 |
| src/application\_agent/models.py         |       76 |        6 |     92% |51-52, 147-149, 162 |
| src/application\_agent/preferences.py    |       84 |       71 |     15% |13-15, 19-20, 25-39, 43-50, 55-62, 66-68, 72-86, 91-125 |
| src/application\_agent/profile.py        |       55 |       38 |     31% |26-36, 41-48, 52-57, 62-70, 75-93 |
| src/application\_agent/storage.py        |       33 |        0 |    100% |           |
| src/application\_agent/tools.py          |       15 |        9 |     40% |     29-40 |
| **TOTAL**                                |  **752** |  **441** | **41%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/Meilocora/Application_Agent/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/Meilocora/Application_Agent/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Meilocora/Application_Agent/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/Meilocora/Application_Agent/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2FMeilocora%2FApplication_Agent%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/Meilocora/Application_Agent/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.