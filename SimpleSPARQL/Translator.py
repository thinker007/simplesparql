from SimpleSPARQL import SimpleSPARQL
from Namespaces import Namespaces
from PrettyQuery import prettyquery
from Parser import Parser

from rdflib import URIRef

from itertools import izip
import copy, time, random

class Translator :
	def __init__(self, cache) :
		self.n = Namespaces()
		#self.n.bind('var', '<http://dwiel.net/axpress/var/0.1/>')
		#self.n.bind('tvar', '<http://dwiel.net/axpress/translation/var/0.1/>')
		#self.n.bind('bnode', '<http://dwiel.net/axpress/bnode/0.1/>')
		#self.n.bind('meta', '<http://dwiel.net/axpress/meta/0.1/>')
		
		self.cache = cache
		self.parser = Parser()

		self.translations = []
		#self.sparql = sparql

	def register_translation(self, translation) :
		n = self.n
		
		# make sure all of the required keys are present
		required = [n.meta.input, n.meta.output, n.meta.function, n.meta.name]
		missing = [key for key in required if key not in translation]
		if missing :
			raise Exception('translation is missing keys: %s' % prettyquery(missing))
		
		# parse any string expressions
		translation[n.meta.input] = self.parser.parse_query(translation[n.meta.input])
		translation[n.meta.output] = self.parser.parse_query(translation[n.meta.output])
		
		print translation[n.meta.name]
		print prettyquery(translation[n.meta.input])
		print prettyquery(translation[n.meta.output])
		print
		
		self.translations.append(translation)
		
	def is_meta_var(self, data) :
		if type(data) == URIRef :
			if data.find(self.n.var) == 0 :
				return True
		return False
	
	def is_var(self, data) :
		if type(data) == URIRef :
			if data.find(self.n.var) == 0 :
				return True
		return False
	
	def meta_var(self, data) :
		if is_meta_var(data) :
			return data[len(self.n.var):]
		return None
	
	def var(self, data) :
		if is_var(data) :
			return data[len(self.n.var):]
		return None
	
	def values_match(self, value, qvalue) :
		# if this is a meta-var, then anything matches
		# TODO: keep track of values of meta-vars to make sure they are consistant
		# throughout.  This will actually require a backtracking search ...
		if type(value) == URIRef :
			if value.find(self.n.var) == 0 :
				return True
			# if this meta value is a variable, see what it is
			if value.find(self.n.var) == 0 :
				if value in self.vars :
					# TODO deal with this some other way
					raise Exception('this var is bound twice ...' + value + ' : '+str(qvalue))
				self.vars[value] = qvalue
				return True
		if value == qvalue :
			return True
	
	def triples_match(self, triple, qtriple) :
		for tv, qv in izip(triple, qtriple) :
			if not self.values_match(tv, qv) :
				return False
		return True
	
	def find_triple_match(self, triple, query) :
		for qtriple in query :
			if self.triples_match(triple, qtriple) :
				return True
		return False
	
	def get_binding(self, triple, qtriple) :
		binding = {}
		for t, q in izip(triple, qtriple) :
			if self.is_meta_var(t) :
				# if the same meta_var is trying to be bound to two different values, 
				# not a valid binding
				if t in binding and binding[t] != q :
					return {}
				binding[t] = q
			elif t != q :
				return {}
		return binding
	
	def find_bindings(self, triple, query) :
		# return [x for x in [get_binding(triple, qtriple) for qtriple in query] if x]
		bindings = []
		for qtriple in query :
			binding = self.get_binding(triple, qtriple)
			if binding and binding not in bindings :
				bindings.append(binding)
		
#		bindings = [binding for binding in bindings if binding]
		return bindings
	
	def conflicting_bindings(self, a, b) :
		"""
		a and b are dictionaries.  Returns True if there are keys which are in 
		both a and b, but have different values
		"""
		for k, v in a.iteritems() :
			if k in b and b[k] != v :
				return True
		return False
	
	def has_already_executed(self, history, translation, binding) :
		return [translation, binding] in history
	
	def register_executed(self, history, translation, binding) :
		history.append([translation, copy.copy(binding)])
		
	def find_meta_vars(self, query) :
		try :
			iter = query.__iter__()
		except AttributeError :
			if type(query) == URIRef :
				if query.find(self.n.var) == 0 :
					return set([query[len(self.n.var):]])
			return set()
		
		vars = set()
		for i in iter :
			vars.update(self.find_meta_vars(i))
		return vars

	def bind_meta_vars(self, translation, query, bindings = []) :
		"""
		input:
			translation : a list of triples (the translation)
			query : a list of triples (the query)
			bindings : a list of possible bindings (dict) thus far
		returns matches, bindings
		matches is True if the query matches the translation
		bindings is a list of bindings for meta_var to value
		"""
		print 'translation',prettyquery(translation)
		print 'q',prettyquery(query)
		bindings = [{}]
		for ttriple in translation :
			print 't',prettyquery(ttriple)
			possible_bindings = self.find_bindings(ttriple, query)
			print 'p',prettyquery(possible_bindings)
			new_bindings = []
			# see if any of the next_bindings fit with the existing bindings
			for pbinding in possible_bindings :
				# if there are no values in bindings that already have some other 
				# value in bindings 
				for binding in bindings :
					if not self.conflicting_bindings(binding, pbinding) :
						# WARNING: this isn't going to copy the values of the bindings!!!
						new_binding = copy.copy(binding)
						#print prettyquery(new_binding)
						#print prettyquery(pbinding)
						#print
						new_binding.update(pbinding)
						if new_binding not in new_bindings :
							new_bindings.append(new_binding)
			bindings = new_bindings
			print 'bindings',prettyquery(bindings)
			print
		
		# get a set of all meta_vars
		meta_vars = self.find_meta_vars(translation)
		
		# if there are no meta_vars, this does still match, but there are no bindings
		if len(meta_vars) == 0 :
			return True, []
		
		# keep only the bindings which contain bindings for all of the meta_vars
		bindings = [binding for binding in bindings if len(binding) == len(meta_vars)]
		
		# if there are no bindings (and there are meta_vars), failed to find a match
		if len(bindings) == 0 :
			return False, []
		
		return True, bindings
	
	def testtranslation(self, translation, query) :
#		print 'testing', translation[self.n.meta.name]
		# check that all of the translation inputs match part of the query
		for triple in translation[self.n.meta.input] :
			if not self.find_triple_match(triple, query) :
				return False, None
		
		# find all possible bindings for the meta_vars if any exist
		matches, bindings = self.bind_meta_vars(translation[self.n.meta.input], query)
		
		return matches, bindings
	
	def sub_bindings_value(self, value, bindings) :
		if value in bindings :
			return bindings[value]
		return value
	
	def next_bnode(self) :
		return self.n.bnode[str(time.time()).replace('.','') + '_' +  str(random.random()).replace('.','')]
	
	def explode_triple(self, triple) :
		"""
		explode_triple([1, [2, 3], [1, 2]]) -->
		[
			[1, 2, 1],
			[1, 3, 1],
			[1, 2, 2],
			[1, 3, 2]
		]
		explode_triple([1, [2, {1 : 2}], [1, 2]]) -->
		[
			[ 1, 2, 1, ],
			[ 1, 2, 2, ],
			[ 1, n.bnode.123083579593_0472807752819, 1, ],
			[ 1, n.bnode.123083579593_00654954466184, 2, ],
			[ n.bnode.123083579593_0472807752819, 1, 2, ],
			[ n.bnode.123083579593_00654954466184, 1, 2, ],
		]
		"""
		# convert each value to a list of values unless it is already a list
		triple = [type(value) == list and value or [value] for value in triple]
		
		triples = [[i] for i in triple[0]]
		
		new_triples = []
		
		for t in triples :
			for i in triple[1] :
				new_triples.append(t + [i])
		
		triples = new_triples
		new_triples = []
		for t in triples :
			for i in triple[2] :
				new_triples.append(t + [i])
		
		# TODO: only one layer of bnodes for now ...
		# TODO: should these bnodes or vars?
		# TODO: should each dict be mapped to only one bnode over the entire process
		#   see above example for how only one dict gets mapped to multiple bnodes
		for t in range(len(new_triples)) :
			for vi in range(3) :
				if type(new_triples[t][vi]) == dict :
					d = new_triples[t][vi]
					b = self.next_bnode()
					new_triples[t][vi] = b
					for k, v in d.iteritems() :
						new_triples.append([b, k, v])
		
		return new_triples
	
	def sub_bindings_triple(self, triple, bindings) :
		triple = [self.sub_bindings_value(value, bindings) for value in triple]
		return self.explode_triple(triple)
	
	def sub_var_bindings(self, output, output_bindings) :
		for bindings in output_bindings :
			for triple in output :
				yield [bound_triple for bound_triple in self.sub_bindings_triple(triple, bindings)]
		
	def find_paths(self, query, find_vars) :
		for possible_translation in possible_translations :
			something = find_paths(possible_translation, find_vars)
	
	# return all triples which have at least one var
	def find_var_triples(self, query) :
		return [triple for triple in query if any(map(lambda x:self.is_var(x), triple))]
	
	# return all triples which have at least one var
	def find_specific_var_triples(self, query, vars) :
		return [triple for triple in query if any(map(lambda x:x in vars, triple))]

	def apply_translation_binding(self, translation, bindings, history) :
		n = self.n
		translation_bindings = []
		for binding in bindings :
			# print 'history',prettyquery([[t[0][n.meta.name], t[1]] for t in history]),
			# print 'now',prettyquery([translation[n.meta.name], binding]),
			if [translation, binding] not in history :
				print 'applying',translation[n.meta.name]
				print 'binding',prettyquery(binding)
				history.append([translation, copy.copy(binding)])
				
				# if this translation expects to be cached, use a cache
				if n.cache.expiration_length in translation :
					output_bindings_list = self.cache.call(translation, binding)					
				else :
					# convert the binding key from n.var.keys to 'keys'
					string_binding = dict([(var[len(self.n.var):], value) for var, value in binding.iteritems()])
					
					# call the function
					output_bindings = translation[n.meta.function](string_binding)
					
					# make sure the output_bindings is a list of possible bindings.
					# this allows a plugin to simply modify the binding passed in
					# or return a new set if that is easier
					if output_bindings == None :
						output_bindings = string_binding
					if type(output_bindings) == dict :
						output_bindings_list = [output_bindings]
					else :
						output_bindings_list = output_bindings
					
					# convert the binding key from 'keys' to n.var.keys
					output_bindings_list = [dict([(self.n.var[var], value) for var, value in output_bindings.iteritems()]) for output_bindings in output_bindings_list]
				
				#print 'output_bindings_list',prettyquery(output_bindings_list),
				
				outtriple_sets = self.sub_var_bindings(translation[n.meta.output], output_bindings_list)
				#outtriple_sets = [x for x in outtriple_sets]
				#print 'outtriple_sets',prettyquery(outtriple_sets)
				translation_bindings.extend(outtriple_sets)
				#print 'translation_bindings',prettyquery(translation_bindings)
		return translation_bindings
	
	def read_translations_helper(self, query, var_triples, bound_var_triples = [], history = []) :
		n = self.n		
		# TODO: a list of values in a set of bound vars should opperate as a list of
		#  values which occur simultaneously.  A plugin can denote that there are 
		#  mutliple possibilities by returning a list of bindings.  Right now, both
		#  cases are treated as occuring simultaneously
		
		# updated once at the end of each iteration.  This will have more than one
		# set of bindings iff one translation has multiple possible bindings
		final_bindings = [query]
		
		found_match = True
		while found_match :
#			print '--- new iteration ---'
			all_new_final_bindings = []
			for query in final_bindings :
				new_final_bindings = [query]
				all_bindings  = [(translation, self.testtranslation(translation, query)) for translation in self.translations]
				found_match = False
				for (translation, (matches, bindings)) in all_bindings :
					if matches :
						this_translation_bindings = self.apply_translation_binding(translation, bindings, history)
#						print 'translation', translation[n.meta.name]
#						print 'this_translation_bindings', prettyquery(this_translation_bindings),
						# 'multiply' each new binding with each previously existing binding
						if len(this_translation_bindings) != 0 :
							#print translation[n.meta.name], len(this_translation_bindings), prettyquery(this_translation_bindings),
							found_match = True
							
							tmp_new_final_bindings = []
							for binding in new_final_bindings :
								for new_binding in this_translation_bindings :
									tmp_new_final_bindings.append(binding + new_binding)
							new_final_bindings = tmp_new_final_bindings
							print 'new_final_bindings',prettyquery(new_final_bindings)
							
				all_new_final_bindings.extend(new_final_bindings)
			
			final_bindings = all_new_final_bindings
			#print 'final_bindings', prettyquery(final_bindings)
		
		# print 'final_bindings',prettyquery(final_bindings),
		return final_bindings
		#exit()
	
	def read_translations(self, query, find_vars = []) :
		if find_vars == [] :
			var_triples = self.find_var_triples(query)
		else :
			var_triples = self.find_specific_var_triples(query, find_vars)
		
		query = self.parser.parse_query(query)
		
		return self.read_translations_helper(query, var_triples, [], [])
		
		# look for all possible routes through the translations to see which paths
		#   might provide an output
		#		* how to deal with cycles?
		#		* how to deal with translations which result in nearly anything (aka possible paths explode to be every possible translation permuted infinite times)
		# paths = self.find_paths(query, find_vars)
		# evaluate those
		# 
		# evaluate all possible routes
		# 
		# look for all possible bindings of these vars
		# iterate through every possible translation of this query
		#   if this translation matches the output
		#			add the bindings to the bindings
		
		#return bindings
		return []
		
