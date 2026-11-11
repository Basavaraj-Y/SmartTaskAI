
import torch
from torch import nn

device = torch.device("mps")

# Create neural network
model = nn.Sequential(
    nn.Linear(10, 32),
    nn.ReLU(),
    nn.Linear(32, 4)
).to(device)

# Sample input and target
X = torch.randn(16, 10, device=device)
y = torch.randint(0, 4, (16,), device=device)

# Training configuration
criterion = nn.CrossEntropyLoss()
optimizer = torch.optim.Adam(
    model.parameters(),
    lr=0.001
)

# Training
optimizer.zero_grad()

outputs = model(X)
loss = criterion(outputs, y)

loss.backward()
optimizer.step()

print("Device:", device)
print("Training loss:", loss.item())
print("Neural network training test successful!")
