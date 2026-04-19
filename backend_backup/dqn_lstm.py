import torch
import torch.nn as nn


class DQNLSTM(nn.Module):
    def __init__(self, input_dim, action_dim):
        super().__init__()

        self.lstm = nn.LSTM(input_dim, 32, batch_first=True)
        self.fc = nn.Linear(32, action_dim)

    def forward(self, x):
        out, _ = self.lstm(x)
        out = out[:, -1, :]
        return self.fc(out)
