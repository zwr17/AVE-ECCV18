import torch
import torch.autograd as autograd
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable
from torch.nn import init

class att_Net(nn.Module):
    def __init__(self, embedding_dim, hidden_dim, hidden_size, tagset_size):
        super(att_Net, self).__init__()
        self.hidden_dim = hidden_dim
        self.lstm_audio = nn.LSTM(128, hidden_dim, 1, batch_first=True, bidirectional=True)
        self.lstm_video = nn.LSTM(512, hidden_dim, 1, batch_first=True, bidirectional=True)

        self.relu = nn.ReLU()
        self.affine_audio = nn.Linear(128, hidden_size)
        """Linear(in_features=128, out_features=512, bias=True)"""
        self.affine_video = nn.Linear(512, hidden_size)
        """Linear(in_features=512, out_features=512, bias=True)"""
        self.affine_v = nn.Linear(hidden_size, 49, bias=False)
        """Linear(in_features=512, out_features=49, bias=False)"""
        self.affine_g = nn.Linear(hidden_size, 49, bias=False)
        """Linear(in_features=512, out_features=49, bias=False)"""
        self.affine_h = nn.Linear(49, 1, bias=False)
        """Linear(in_features=49, out_features=1, bias=False)"""


        self.L1 = nn.Linear(hidden_dim * 4, 64)
        """Linear(in_features=512, out_features=64, bias=True)"""
        self.L2 = nn.Linear(64, tagset_size)
        """Linear(in_features=64, out_features=29, bias=True)"""

        self.init_weights()
        if torch.cuda.is_available():
            self.cuda()

    def init_weights(self):
        """Initialize the weights."""
        init.xavier_uniform(self.affine_v.weight)
        init.xavier_uniform(self.affine_g.weight)
        init.xavier_uniform(self.affine_h.weight)

        init.xavier_uniform(self.L1.weight)
        init.xavier_uniform(self.L2.weight)
        init.xavier_uniform(self.affine_audio.weight)
        init.xavier_uniform(self.affine_video.weight)

    def forward(self, audio, video):
        #audio torch.Size([402, 10, 128])
        #video torch.Size([402, 10, 7, 7, 512])

        v_t = video.view(video.size(0) * video.size(1), -1, 512)
        V = v_t
        #V torch.Size([4020, 49, 512])

        # Audio-guided visual attention
        v_t = self.relu(self.affine_video(v_t))#torch.Size([4020, 49, 512])
        a_t = audio.view(-1, audio.size(-1))#torch.Size([4020, 512])
        a_t = self.relu(self.affine_audio(a_t))#torch.Size([4020, 512])
        content_v = self.affine_v(v_t) \
                    + self.affine_g(a_t).unsqueeze(2) #torch.Size([4020, 49, 49])

        z_t = self.affine_h((F.tanh(content_v))).squeeze(2)#torch.Size([4020, 49])
        alpha_t = F.softmax(z_t, dim=-1).view(z_t.size(0), -1, z_t.size(1)) # attention map
        # torch.Size([4020, 1, 512])
        c_t = torch.bmm(alpha_t, V).view(-1, 512)#bnm矩阵乘法
        # torch.Size([4020, 512])
        video_t = c_t.view(video.size(0), -1, 512) #attended visual features
        # torch.Size([402,10,512])

        # Bi-LSTM for temporal modeling
        hidden1 = (autograd.Variable(torch.zeros(2, audio.size(0), self.hidden_dim).cuda()),
                   autograd.Variable(torch.zeros(2, audio.size(0), self.hidden_dim).cuda()))
        #
        hidden2 = (autograd.Variable(torch.zeros(2, audio.size(0), self.hidden_dim).cuda()),
                   autograd.Variable(torch.zeros(2, audio.size(0), self.hidden_dim).cuda()))
        self.lstm_video.flatten_parameters()#Resets parameter data pointer so that they can use faster code paths
        self.lstm_audio.flatten_parameters()
        lstm_audio, hidden1 = self.lstm_audio(
            audio.view(len(audio), 10, -1), hidden1)
        #lstm_audio  torch.Size([402, 10, 256])
        lstm_video, hidden2 = self.lstm_video(
            video_t.view(len(video), 10, -1), hidden2)
        # lstm_video  torch.Size([402, 10, 256])

        # concatenation and prediction
        output = torch.cat((lstm_audio, lstm_video), -1)
        output = self.relu(output)
        #output torch.Size([402, 10, 512])
        out = self.L1(output)
        out = self.relu(out)
        out = self.L2(out)
        out = F.softmax(out, dim=-1)
        #out torch.Size([402, 10, 29])

        from IPython import embed
        embed()

        return out