# r-place

A collaborative pixel art canvas inspired by Reddit's r/Place, where users can place colored pixels on a shared canvas and see real-time updates from other users.

## 🎨 What is r-place?

r-place is a real-time collaborative pixel art project where:
- Users can place one colored pixel at a time on a shared canvas
- Real-time updates show pixels placed by other users instantly
- Rate limiting prevents spam (5-minute cooldown between pixel placements)
- The canvas persists and grows into collaborative artwork over time

## 🏗️ Project Versions

This repository contains two different implementations:

### Version 1 (place_v1) - Docker/EC2 Based
A simpler implementation using:
- **Frontend**: Static HTML/CSS/JavaScript with jQuery
- **Backend**: Node.js Express servers
- **WebSocket Server**: Real-time pixel updates
- **Infrastructure**: Docker containers, EC2, API Gateway, Lambda
- **Deployment**: Docker Compose with nginx reverse proxy

### Version 3 (place_v3) - AWS Serverless
A more sophisticated cloud-native implementation using:
- **Frontend**: Static files served via CloudFront + S3
- **API**: HTTP and WebSocket API Gateway endpoints
- **Backend**: AWS Lambda functions for all server logic
- **Real-time**: WebSocket connections for live updates
- **Storage**: 
  - ElastiCache (ValKey) for fast in-memory board state and rate limiting
  - DynamoDB for persistent pixel history
  - SQS for decoupled message processing
- **Infrastructure**: VPC with private subnets for security

## 🚀 Features

- **Real-time Collaboration**: See other users' pixels appear instantly
- **Rate Limiting**: 5-minute cooldown between pixel placements per user
- **Persistent Canvas**: Board state is maintained and pixel history is stored
- **Scalable Architecture**: Handles multiple concurrent users
- **Color Selection**: Choose from a palette of colors for pixel placement
- **Canvas Navigation**: Pan and zoom around the pixel canvas

## 🛠️ Technology Stack

### Version 1
- **Frontend**: HTML5 Canvas, jQuery, CSS
- **Backend**: Node.js, Express.js
- **WebSockets**: Socket.io for real-time communication
- **Infrastructure**: Docker, nginx, AWS EC2, API Gateway, Lambda
- **Deployment**: Docker Compose

### Version 3
- **Frontend**: HTML5 Canvas, jQuery, vanilla JavaScript
- **Backend**: AWS Lambda (Python), API Gateway
- **Real-time**: WebSocket API Gateway
- **Cache**: ElastiCache (ValKey/Redis) with IAM authentication
- **Database**: DynamoDB for pixel history
- **Queue**: SQS for asynchronous processing
- **CDN**: CloudFront for global content delivery
- **Storage**: S3 for static assets

## 📁 Project Structure

```
├── README.md
├── place_v1/                    # Docker/EC2 implementation
│   ├── docker-compose.yml      # Container orchestration
│   ├── setup.md                # V1 setup instructions
│   ├── lambda/                 # AWS Lambda functions
│   ├── nginx/                  # Reverse proxy configuration
│   ├── socketServer/           # WebSocket server (Node.js)
│   └── webServer/              # Static file server (Node.js)
└── place_v3/                   # AWS Serverless implementation
    ├── docker-compose.yml      # Local development
    ├── docs/                   # Architecture and setup docs
    ├── frontend/               # Static web assets
    ├── lambda/                 # Lambda functions (Python)
    ├── socketServer/           # WebSocket development server
    └── webServer/              # Static development server
```

## 🚦 Getting Started

### Quick Start (Version 1 - Docker)
1. Navigate to the `place_v1` directory
2. Run `docker-compose up` to start the services
3. Access the application at `http://localhost:8080`

### Production Deployment (Version 3 - AWS)
1. Follow the setup guide in [`place_v3/docs/setup.md`](place_v3/docs/setup.md)
2. Configure AWS resources (VPC, Lambda, API Gateway, etc.)
3. Deploy using AWS CloudFormation or CDK
4. Update frontend endpoints in [`place_v3/frontend/index.html`](place_v3/frontend/index.html)

## 📚 Documentation

- **Version 1 Setup**: [`place_v1/setup.md`](place_v1/setup.md) - Detailed AWS setup instructions
- **Version 3 Setup**: [`place_v3/docs/setup.md`](place_v3/docs/setup.md) - Serverless deployment guide  
- **Architecture**: [`place_v3/docs/architecture.txt`](place_v3/docs/architecture.txt) - System design overview

## 🎮 How to Use

1. **Load the Canvas**: The application fetches the current board state on page load
2. **Select a Color**: Choose your desired pixel color from the palette
3. **Place a Pixel**: Click on any empty or existing pixel location
4. **Wait for Cooldown**: Each user can place one pixel every 5 minutes
5. **Watch Live Updates**: See pixels from other users appear in real-time

## 🔧 Local Development

### Version 1
```bash
cd place_v1
docker-compose up --build
```

### Version 3
```bash
cd place_v3
# Start the development servers
cd socketServer && npm start &
cd webServer && npm start &
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is open source and available under the MIT License.

---

*Inspired by Reddit's r/Place - a social experiment in collaborative creation.*