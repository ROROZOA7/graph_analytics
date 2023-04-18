import tensorflow as tf
import math,logging
from pprint import  pprint
from time import time

class pvdm(object):
    '''
    skipgram model - refer Mikolov et al (2013)
    '''

    def __init__(self,num_graphs,num_subgraphs,learning_rate,embedding_size,
                 num_negsample,num_steps,corpus):
        self.num_graphs = num_graphs
        self.num_subgraphs = num_subgraphs
        self.embedding_size = embedding_size
        self.num_negsample = num_negsample
        self.learning_rate = learning_rate
        self.num_steps = num_steps
        self.corpus = corpus
        self.graph, self.batch_inputs_g, self.batch_inputs_sg, self.batch_labels,self.normalized_embeddings,\
        self.loss,self.optimizer = self.trainer_initial()


    def trainer_initial(self):
        graph = tf.Graph()
        with graph.as_default():
            batch_inputs_g = tf.placeholder(tf.int32, shape=([None, ]))
            batch_input_sg = tf.placeholder(tf.int32, shape=([None, ]))
            batch_labels = tf.placeholder(tf.int64, shape=([None, 1]))

            graph_embeddings = tf.Variable(
                    tf.random_uniform([self.num_graphs, self.embedding_size], -0.5 / self.embedding_size, 0.5/self.embedding_size))

            subgraph_embedding = tf.Variable(
                    tf.random_uniform([self.num_subgraphs, self.embedding_size], -0.5 / self.embedding_size, 0.5/self.embedding_size)
            )

            batch_graph_embeddings = tf.nn.embedding_lookup(graph_embeddings, batch_inputs_g) #hiddeb layer
            batch_subgraph_embedding = tf.nn.embedding_lookup(subgraph_embedding, batch_input_sg)

            # Concatenate the two embeddings matrices
            embeddings_concat = tf.concat([batch_graph_embeddings, batch_subgraph_embedding], axis=1)

            weights = tf.Variable(tf.truncated_normal([self.num_subgraphs, self.embedding_size * 2],
                                                          stddev=1.0 / math.sqrt(self.embedding_size))) #output layer wt
            biases = tf.Variable(tf.zeros(self.num_subgraphs)) #output layer biases

            #negative sampling part
            loss = tf.reduce_mean(
                tf.nn.nce_loss(weights=weights,
                               biases=biases,
                               labels=batch_labels,
                               inputs=embeddings_concat,
                               num_sampled=self.num_negsample,
                               num_classes=self.num_subgraphs,
                               sampled_values=tf.nn.fixed_unigram_candidate_sampler(
                                   true_classes=batch_labels,
                                   num_true=1,
                                   num_sampled=self.num_negsample,
                                   unique=True,
                                   range_max=self.num_subgraphs,
                                   distortion=0.75,
                                   unigrams=self.corpus.subgraph_id_freq_map_as_list)#word_id_freq_map_as_list is the
                               # frequency of each word in vocabulary
                               ))

            global_step = tf.Variable(0, trainable=False)
            learning_rate = tf.train.exponential_decay(self.learning_rate,
                                                       global_step, 100000, 0.96, staircase=True) #linear decay over time

            learning_rate = tf.maximum(learning_rate,0.001) #cannot go below 0.001 to ensure at least a minimal learning

            optimizer = tf.train.GradientDescentOptimizer(learning_rate).minimize(loss,global_step=global_step)

            norm = tf.sqrt(tf.reduce_mean(tf.square(graph_embeddings), 1, keep_dims=True))
            normalized_embeddings = graph_embeddings/norm

        return graph,batch_inputs_g, batch_input_sg, batch_labels, normalized_embeddings, loss, optimizer



    def train(self,corpus,batch_size):
        with tf.Session(graph=self.graph,
                        config=tf.ConfigProto(log_device_placement=True,allow_soft_placement=False)) as sess:

            init = tf.global_variables_initializer()
            sess.run(init)

            loss = 0

            for i in xrange(self.num_steps):
                t0 = time()
                step = 0
                while corpus.epoch_flag == False:
                    # batch_data, batch_labels = corpus.generate_batch_from_file(batch_size)# get (target,context) wordid tuples
                    batch_data, batch_context, batch_labels = corpus.generate_batch_pvdm(batch_size)  # get (target, context, output) wordid tuples


                    feed_dict = {self.batch_inputs_g:batch_data,self.batch_inputs_sg:batch_context, self.batch_labels:batch_labels}
                    _,loss_val = sess.run([self.optimizer,self.loss],feed_dict=feed_dict)

                    loss += loss_val

                    if step % 100 == 0:
                        if step > 0:
                            average_loss = loss/step
                            logging.info( 'Epoch: %d : Average loss for step: %d : %f'%(i,step,average_loss))
                    step += 1

                corpus.epoch_flag = False
                epoch_time = time() - t0
                logging.info('#########################   Epoch: %d :  %f, %.2f sec.  #####################' % (i, loss/step,epoch_time))
                loss = 0

            #done with training
            final_embeddings = self.normalized_embeddings.eval()
        return final_embeddings