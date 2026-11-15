# Multi-AZ High Availability and Serverless Architecture on AWS

**Author:** Esther Blessing Durojaye
**Region:** Europe (Ireland), `eu-west-1`
**Stack name:** `ha-serveless`

A fault-tolerant AWS environment defined as code with AWS SAM (CloudFormation): a multi-AZ web tier with load balancing and auto-scaling, plus a serverless backend (API Gateway, Lambda, S3 event trigger, DynamoDB).

## Requirements covered

| Requirement | How it is met |
|---|---|
| VPC with subnets in different Availability Zones | VPC `10.0.0.0/16` with a public and a private subnet in each of two AZs |
| Load balancing | Internet-facing Application Load Balancer across both public subnets |
| Auto-scaling | Auto Scaling Group (min 2, max 4) with CPU target-tracking at 50% |
| Serverless app with an event source | Lambda functions triggered by an HTTP API request and by an S3 upload |
| Serverless database | DynamoDB table, on-demand capacity |

## Repository contents

| File | Purpose |
|---|---|
| `template.yaml` | All infrastructure and configuration (SAM/CloudFormation) |
| `api_handler.py` | Lambda code for the HTTP API (create/read items) |
| `s3_processor.py` | Lambda code triggered by S3 uploads |
| `screenshots/` | Evidence screenshots referenced below |

## Architecture

```
                         Internet
                            |
          +-----------------+------------------+
          |                                    |
   Application Load Balancer            API Gateway (HTTP API)
   (spans both public subnets)                  |
          |                                     v
 +--------+-----------------+            Lambda: ApiFunction
 |  VPC 10.0.0.0/16         |                    |
 |                          |                    v
 |  AZ-a            AZ-b    |            DynamoDB: ItemsTable  <---+
 |  Public  10.0.0.0/24  Public  10.0.1.0/24    (on-demand,        |
 |   NAT-a               NAT-b   |                PITR, SSE)       |
 |  Private 10.0.10.0/24 Private 10.0.11.0/24                      |
 |   EC2 (ASG)           EC2 (ASG)                                 |
 +--------------------------+                                      |
                                                                   |
   S3 UploadBucket --ObjectCreated--> Lambda: ProcessorFunction ---+
```

### Network

| Component | Details |
|---|---|
| Public subnets | `10.0.0.0/24` (AZ a), `10.0.1.0/24` (AZ b); host the load balancer and NAT gateways |
| Private subnets | `10.0.10.0/24` (AZ a), `10.0.11.0/24` (AZ b); host the web servers, no public IPs |
| NAT gateways | One per AZ with its own route table, so an AZ failure does not cut outbound access in the other AZ |
| Security groups | ALB group allows HTTP from the internet; app group allows HTTP only from the ALB group |

### Load balancing and auto-scaling

- Application Load Balancer on port 80, health check on `/` every 15 seconds (unhealthy after 2 failures).
- Launch template on Amazon Linux 2023, IMDSv2 required, SSM role (no SSH keys). User data installs Apache and serves a page showing the instance ID and AZ.
- Auto Scaling Group: min 2, desired 2, max 4, across both private subnets, with ELB health checks so failed instances are replaced.
- Target-tracking policy keeps average CPU at 50%.

### Serverless components

| Component | Purpose |
|---|---|
| API Gateway (HTTP API) | Routes `POST /items`, `GET /items`, `GET /items/{id}` to `ApiFunction` |
| `ApiFunction` (Python 3.12) | Creates and reads items in DynamoDB |
| S3 bucket | Event source; encrypted, public access blocked |
| `ProcessorFunction` (Python 3.12) | Triggered by `s3:ObjectCreated:*`; stores file metadata in DynamoDB |
| DynamoDB `ItemsTable` | Partition key `id` (String), on-demand billing, encryption at rest, point-in-time recovery |
| IAM roles | Least-privilege access through SAM policy templates |

### Fault tolerance

- Subnets, NAT gateways, load balancer and web servers all span two AZs.
- If an instance or an entire AZ fails, the load balancer routes traffic to the healthy AZ.
- The Auto Scaling Group replaces failed instances and scales out under load.
- API Gateway, Lambda, S3 and DynamoDB are regional managed services that run across multiple AZs.

## Deployment

Deployed from AWS CloudShell (SAM CLI is preinstalled).

1. Upload `template.yaml`, `api_handler.py` and `s3_processor.py` to CloudShell.
2. Run:
   ```bash
   sam build
   sam deploy --guided
   ```
3. Answers used: stack name `ha-serveless`, region `eu-west-1`, accept the parameter defaults, confirm changes `N`, allow IAM role creation `Y`, disable rollback `N`, API without authentication `y`, save arguments `Y`.
4. Wait about 8 to 10 minutes. The NAT gateways take the longest.

**Issue fixed during deployment:** the first deploy failed with a circular dependency between the S3 bucket, the trigger permission and the processor function's IAM role. It was resolved by giving the bucket a fixed name and referencing that name, instead of the bucket resource, in the function's S3 read policy.

### Stack outputs

| Output | Value |
|---|---|
| `AlbUrl` | `http://ha-serve-Alb-fZ2zJw2vH9qO-18913034.eu-west-1.elb.amazonaws.com` |
| `ApiUrl` | `https://sy303i5yxf.execute-api.eu-west-1.amazonaws.com/items` |
| `UploadBucketName` | `ha-serverless-uploads-775187663402-eu-west-1` |
| `TableName` | `ha-serveless-ItemsTable-11CY6IILJGKNB` |

## Testing and evidence

### 1. Load balancer

Open the `AlbUrl` in a browser and refresh. The page shows which instance and AZ served the request.

![Served from eu-west-1a](screenshots/highly%20az%202.jpeg)
![Served from eu-west-1b](screenshots/highly%20az%201.jpeg)

### 2. Serverless API (HTTP request event source)

```bash
curl -X POST https://sy303i5yxf.execute-api.eu-west-1.amazonaws.com/items \
  -H "Content-Type: application/json" \
  -d '{"name":"test item","description":"hello"}'

curl https://sy303i5yxf.execute-api.eu-west-1.amazonaws.com/items
```

The POST returned the created item (`id` 412638ef-52e7-4f1d-bfbb-5938f88a34e0) and the GET returned it in the list, confirming API Gateway, Lambda and DynamoDB work together.


### 3. S3 upload event source

```bash
echo "hello" > test.txt
aws s3 cp test.txt s3://ha-serverless-uploads-775187663402-eu-west-1/test.txt
aws dynamodb scan --table-name ha-serveless-ItemsTable-11CY6IILJGKNB
```

The scan returned two items: the API item (`source: api`) and a new item written by `ProcessorFunction` (`source: s3-upload`, `name: test.txt`). The S3 event triggered the Lambda function, which wrote to DynamoDB.


### 4. Multi-AZ infrastructure in the console

![VPC resource map](screenshots/VPC.jpeg)
![Load balancer network mapping](screenshots/load%20balancer.jpeg)
![Target group, 2 healthy targets](screenshots/target%20group.jpeg)
![Auto Scaling policy](screenshots/auto-scaling.jpeg)
![ApiFunction and its triggers](screenshots/API%20lambda.jpeg)
![ProcessorFunction and its S3 trigger](screenshots/process%20lambda.jpeg)
![DynamoDB table 1](screenshots/dynamo%20table%201.jpeg)
![DynamoDB table 2](screenshots/dynamo%20table%202.jpeg)

### 5. Fault-tolerance demonstration

One of the two web instances was terminated from the EC2 console. The load balancer URL was refreshed during the failure, and the Auto Scaling Group launched a replacement to restore the desired capacity of 2.

![Instances before termination](screenshots/ec2.jpeg)
![Site still serving after termination](screenshots/ec2%20termination.jpeg)
![Replacement instance launched](screenshots/ec2%20autoscaled.jpeg)
![Auto Scaling activity history](screenshots/activity%20tab%20proof.jpeg)

## Clean-up

The two NAT gateways are the main ongoing cost, so the environment was deleted after testing:

```bash
aws s3 rm s3://ha-serverless-uploads-775187663402-eu-west-1 --recursive
sam delete --stack-name ha-serveless
```

## Screenshot checklist

File names below are as saved inside the `screenshots/` folder (all screenshots are `.jpeg` files).

| # | Screenshot required | Your file name |
|---|---|---|
| 1 | Load balancer page served from `eu-west-1a` | highly az 2.jpeg |
| 2 | Load balancer page served from `eu-west-1b` | highly az 1.jpeg |
| 3 | CloudShell: API POST and GET output | not included |
| 4 | DynamoDB scan showing `api` and `s3-upload` items | not included |
| 5 | VPC resource map | VPC.jpeg |
| 6 | Load balancer network mapping (2 AZs) | load balancer.jpeg |
| 7 | Target group: 2 healthy targets | target group.jpeg |
| 8 | Auto Scaling Group: automatic scaling policy | auto-scaling.jpeg |
| 9 | `ApiFunction` in the Lambda console | API lambda.jpeg |
| 10 | `ProcessorFunction` in the Lambda console | process lambda.jpeg |
| 11 | DynamoDB, Explore table items | dynamo table 1.jpeg, dynamo table 2.jpeg |
| 12 | EC2 instances before termination | ec2.jpeg |
| 13 | Load balancer still serving after termination | ec2 termination.jpeg |
| 14 | EC2 instances showing replacement launched | ec2 autoscaled.jpeg |
| 15 | Auto Scaling Group activity history | activity tab proof.jpeg |
